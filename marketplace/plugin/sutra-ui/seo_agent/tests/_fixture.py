"""tests/_fixture.py — what every suite does before it touches the package.

Three things, in one place so no suite drifts from the others. It puts the folder that
holds seo_agent/ on sys.path so a suite can be run as a plain file as well as with -m. It
points the data dir at a throwaway folder, so no test ever writes into a real install. And
it plants a small site index, because learn_voice refuses to run without one and the old
suites leaned on a real crawl that lived in the app's data/ folder.

The model stubs live here too. They match on the literal output keys each prompt asks for,
which is the only reliable signal, because prompts share vocabulary but never share their
output shape.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Four pages, shaped like index_site writes them. Enough text that learn_voice has prose
# to sample, and real-looking URLs so link candidates and the link checks have targets.
_PROSE = ("We build programmes for people who already run things. Every cohort is taught by "
          "practitioners, not lecturers, and every week ends with a decision made on real "
          "numbers. The work is direct. Short briefs, live cases, a room that argues back. "
          "Nobody leaves with a certificate they cannot explain. ") * 6

SITE_INDEX = {
    "domain": "example.com",
    "page_count": 4,
    "pages": [
        {"url": "https://example.com/", "title": "Example: education for operators",
         "description": "Practitioner-led programmes for founders and senior operators.",
         "h1": "Learn by running the numbers", "word_count": 240, "text": _PROSE,
         "top_keyword": "operator education", "position": 4, "keyword_volume": 900},
        {"url": "https://example.com/programmes", "title": "Programmes",
         "description": "Every programme we run, and who it is for.",
         "h1": "Programmes", "word_count": 210, "text": _PROSE,
         "top_keyword": "leadership programme", "position": 11, "keyword_volume": 1200},
        {"url": "https://example.com/blog/what-changes-after", "title": "What changes after a programme",
         "description": "The part nobody writes about: the six months after.",
         "h1": "What changes after", "word_count": 260, "text": _PROSE,
         "top_keyword": "after executive education", "position": 7, "keyword_volume": 300},
        {"url": "https://example.com/about", "title": "About", "description": "Who we are.",
         "h1": "About", "word_count": 190, "text": _PROSE,
         "top_keyword": None, "position": 0, "keyword_volume": 0},
    ],
    "indexed_at": "2026-01-01T00:00:00Z",
}


_BODY = ("# {h1}\nWe build programmes for people who already run things.\n## Who it is for\n"
         "Every cohort is taught by practitioners, not lecturers, and every week ends with a decision "
         "made on real numbers. The work is direct. Short briefs, live cases, a room that argues back.\n"
         "## What changes after\nNobody leaves with a certificate they cannot explain. Decision speed, the "
         "quality of the bench below the founder, and whether a leader can hold a room.\n- Cost per hire drops\n"
         "- Time to decision drops\n") * 3

for _p in SITE_INDEX["pages"]:
    _p.setdefault("body", _BODY.format(h1=_p["h1"]))
    _p.setdefault("body_chars", len(_p["body"]))
    _p.setdefault("body_status", "ok")
    _p.setdefault("type", "page" if _p["url"].count("/") <= 3 else "post")


def plant_content_database():
    """knowledge/content-database.jsonl from the fixture pages, one line per page."""
    import json
    from seo_agent import store
    rows = [{"url": p["url"], "type": p.get("type", "page"), "title": p["title"], "body": p["body"]}
            for p in SITE_INDEX["pages"]]
    store.save_knowledge("content-database.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n")


def stub_voyage():
    """Deterministic, network-free stand-ins for voyage.embed / voyage.rerank.

    A vector is built from the words of the text, so two texts that share words score
    higher, which is all a retrieval test needs. rerank scores by word overlap too."""
    import hashlib
    import numpy as np
    from seo_agent.tools import voyage

    def _vec(text):
        v = np.zeros(64, dtype=np.float32)
        for w in str(text).lower().split():
            v[int(hashlib.md5(w.encode()).hexdigest()[:6], 16) % 64] += 1.0
        return v / (np.linalg.norm(v) + 1e-9)

    def embed(texts, input_type="document"):
        return np.array([_vec(t) for t in texts], dtype=np.float32)

    def rerank(query, docs, top_k):
        q = set(str(query).lower().split())
        scored = [(i, len(q & set(str(d).lower().split())) / (len(q) + 1.0)) for i, d in enumerate(docs)]
        scored.sort(key=lambda x: -x[1])
        return scored[:int(top_k)]

    voyage.embed = embed
    voyage.rerank = rerank
    voyage.available = lambda: True


def setup():
    """Point the data dir at a temp folder and plant the site index. Returns the dir.

    SEO_AGENT_DATA wins when the runner set it, so all suites in one run share a folder
    the same way they shared data/ before. Otherwise each suite gets its own.
    """
    from seo_agent import store
    if not os.environ.get("SEO_AGENT_DATA", "").strip():
        os.environ["SEO_AGENT_DATA"] = tempfile.mkdtemp(prefix="seo-agent-tests-")
    store.set_data_dir(os.environ["SEO_AGENT_DATA"])
    if not store.knowledge("site_index.json"):
        store.save_knowledge("site_index.json", SITE_INDEX)
    # A real install always has a company record after setup, and several tools read it (the
    # competitor derivation, the prompts' brand tokens). Without one the suites test a state
    # that cannot occur once setup has run.
    rec = store.knowledge("brand/company.json") or {}
    if not rec.get("brand_oneliner"):
        rec.setdefault("brand", "Example")
        rec.setdefault("domain", "example.com")
        rec["brand_oneliner"] = "Example — practitioner-led business programmes for founders and senior operators"
        rec.setdefault("niche_definition", "executive education — cohort programmes for operators")
        rec.setdefault("about", "Practitioner-led programmes for people who already run things.")
        store.save_knowledge("brand/company.json", rec)
    import os as _os
    if not _os.path.exists(_os.path.join(store.knowledge_dir(), "content-database.jsonl")):
        plant_content_database()
    stub_write_network()
    return store.data_dir()


# ---- the model stubs -----------------------------------------------------------------

def stub_json(prompt, system=None, retries=1, **kw):
    """Match on the literal output keys each prompt asks for. That is the only reliable
    signal, because prompts share vocabulary but never share their output shape."""
    p = prompt

    w = stub_write_json(p)
    if w is not None:
        return w

    # ---- the brand builders (learn_brand). These sit first because two of their prompts also carry
    # the literal "sections" / "topics" that older branches below match on.
    b = _brand_json(p)
    if b is not None:
        return b

    # ---- the research engine (run_research / build_blueprint). Same rule: literal output keys, and
    # where a prompt's answer must echo the ids or the text it was handed, the stub reads the prompt.
    r = _research_json(p)
    if r is not None:
        return r

    if '"competitors"' in p:
        return {"competitors": [{"domain": "rival-one.com", "why": "same programmes"},
                                {"domain": "rival-two.com", "why": "same buyers"},
                                {"domain": "rival-three.com", "why": "adjacent"}]}

    if '"topics"' in p:
        return {"topics": [{"id": "t%d" % i, "topic": "Topic number %d" % i,
                            "sparked_by": "rival keyword %d" % i,
                            "angle": "what they have not done, in a sentence",
                            "why_us": "it fits what we sell",
                            "est_volume": 400 + i * 90, "est_difficulty": 20 + i}
                           for i in range(1, 7)]}

    if '"what_they_all_cover"' in p:
        return {"what_they_all_cover": ["rankings", "fees", "eligibility", "placement", "alumni"],
                "the_gap": "Nobody writes about what actually changes for the leader afterwards.",
                "recommended_angle": "Lead with the outcome, not the curriculum."}

    if '"primary_keyword"' in p:
        return {"primary_keyword": "executive education india",
                "why": "Best volume against a difficulty we can realistically win.",
                "secondary_keywords": ["executive mba india", "leadership programmes india"]}

    if '"sections"' in p or '"meta_description"' in p:
        return {"title": "Executive Education in India, and What Changes After",
                "meta_description": "What actually changes for a leader after an executive programme.",
                "keyword_placement": "Primary in the H1 and the first paragraph.",
                "sections": [{"id": "s%d" % i, "heading": "Section %d heading" % i,
                              "covers": "what this section covers, in a sentence",
                              "words": 250, "internal_links": []} for i in range(1, 7)]}

    # learn_voice and anything else that describes the company
    return {"company": "Masters' Union", "what_they_sell": "practitioner-led business education",
            "who_buys": "founders, CHROs and senior operators",
            "summary": "Direct and concrete. Short sentences. No corporate padding.",
            "traits": ["direct", "concrete", "unfussy"],
            "avoid": ["delve", "leverage", "robust", "seamless"],
            "examples": ["We teach by doing.", "The classroom is the boardroom."]}


def stub_text(prompt, system=None, **kw):
    """Long enough that a written section looks like a real one."""
    w = stub_write_text(prompt)
    if w is not None:
        return w
    b = _brand_text(prompt)
    if b is not None:
        return b
    r = _research_text(prompt)
    if r is not None:
        return r
    return ("Executive programmes in India have grown quickly, and most of the coverage stops at "
            "rankings and fees. That leaves the question a buyer actually has unanswered.\n\n"
            "What changes after the programme is the part worth writing about. Decision speed, "
            "the quality of the bench below the founder, and whether a leader can hold a room.")


# ---- the brand builders' stubs -------------------------------------------------------------------
# Keyed on the literal output keys each prompt in prompts/brand/ asks for. Kept apart from the older
# branches so a new brand prompt is one more `if` here, never a change to a suite that already passes.
import re as _re

_URL = _re.compile(r"https?://[^\s|)]+")


def _brand_json(p):
    if '"stat_types"' in p:                                   # classify-types
        return {"stat_types": ["page"], "story_types": ["successstory"],
                "commercial_types": ["page", "product", "integration"], "editorial_types": ["post"],
                "notes": "the test fixture's types"}
    if '"bucket": "scale|results|credibility"' in p:          # extract-stats (a list)
        return [{"stat": "Customers", "value": "1,500+", "bucket": "scale", "quote": "Trusted by 1,500+ teams"},
                {"stat": "Time-to-hire cut", "value": "55%", "bucket": "results", "quote": "55% faster time-to-hire"},
                {"stat": "G2 rating", "value": "4.7", "bucket": "credibility", "quote": "4.7 on G2"}]
    if '{"none": true}' in p:                                 # extract-stories
        m = _re.search(r"PAGE URL: (\S+)", p)
        who = (m.group(1) if m else "a customer").rstrip("/").split("/")[-1].title()
        return {"title": "%s cut its hiring time" % who, "story": "%s replaced CV screening with a skills test and "
                "cut its time-to-hire by half in one quarter." % who, "point": "skills-first hiring is faster", "number": "55%"}
    if '"picks"' in p:                                        # pick-pages: every URL in the candidate table
        table = p.split("CANDIDATE TABLE", 1)[-1]
        urls = []
        for u in _URL.findall(table):
            if u not in urls:
                urls.append(u)
        return {"picks": [{"bucket": "A", "bucket_name": "Positioning / commercial", "url": u, "traffic": 0,
                           "note": "fixture pick"} for u in urls]}
    if '"voice_tone"' in p:                                   # extract-evidence
        return {"voice_tone": "direct, confident; cue: 'The work is direct.'",
                "positioning": "practitioner-led programmes for people who already run things",
                "audience_pain": "founders and senior operators tired of certificates they cannot explain",
                "quotable": "Nobody leaves with a certificate they cannot explain.",
                "style_format_cta": "short sentences, short H1s; CTA: \"Apply now\"", "company_dimension": ""}
    if '"brand_oneliner"' in p:                               # draft-oneliner
        return {"brand_oneliner": "Example — practitioner-led business programmes for founders and senior operators",
                "niche_definition": "executive education — programmes for operators, cohort learning, leadership practice"}
    if '"overall_pass"' in p:                                 # the voice and features quality gates
        return {"sections": [{"name": "Brand Voice Pillars", "pass": True, "why": "three pillars, each complete", "redo": ""}],
                "overall_pass": True, "redo_notes": ""}
    if '"headline_case"' in p:                                # analyze-blogs
        n = p.count("### ")
        return {"headline_case": "Sentence case", "brand_naming": "Example, always capitalised",
                "industry_terms": ["skills assessment", "time-to-hire", "cohort"], "oxford_comma": "Yes" if n != 2 else "No",
                "em_dash_usage": "rare; hyphens preferred", "quote_style": "double", "ellipses": "rare",
                "number_style": "numerals for stats", "acronyms": ["ATS", "HR"], "preferred_words": ["operators"],
                "avoided_words": ["leverage", "seamless"]}
    if '"social_proof"' in p:                                 # extract-facts
        m = _re.search(r"PAGE URL: (\S+)", p)
        u = m.group(1) if m else ""
        return {"features": ["Cohort builder: plan a cohort in an afternoon", "Live cases: decide on real numbers"],
                "integrations": ["Slack (chat)"] if "integration" in u else [],
                "pricing": ["Standard: pay per seat; 30-day refund"] if "pricing" in u else [],
                "competitive": ["vs Rival One: practitioners, not lecturers"] if "alternatives" in u or "-vs-" in u else [],
                "social_proof": ["1,500+ teams", "4.7 on G2"], "audience": ["founders; pain: slow decisions"],
                "ctas": ["Apply now", "Book a call"], "faq": ["Can I cancel? → Yes, any time"]}
    if '"what_makes_it_great"' in p:                          # score-article
        m = _re.search(r"URL (\S+)", p)
        u = m.group(1) if m else ""
        off = "thoughts" in u
        return {"score": 3 if off else 8, "verdict": "off-voice" if off else "on-voice",
                "verdict_why": "generic" if off else "direct, proof-backed, second person",
                "what_makes_it_great": [] if off else ["Direct, Backed by Proof — opens on a real number (\"55%\")",
                                                       "Operator's Eye — teaches by a decision, not a definition"],
                "h1": "Article: %s" % (u.rstrip("/").split("/")[-1] or "home")}
    if '"personas"' in p:                                     # persona
        return {"personas": [{"name": "Founder / CEO", "who": "runs a 50-500 person company", "reads": "strategy pieces",
                              "cares_about": "decision speed, the bench", "depth_and_angle": "numbers, trade-offs",
                              "not_this": "HR process detail"},
                             {"name": "Senior Operator", "who": "COO / VP running a function", "reads": "how-to and cases",
                              "cares_about": "what changes in the next quarter", "depth_and_angle": "worked examples",
                              "not_this": "vision talk"},
                             {"name": "CHRO / People Lead", "who": "owns L&D budget", "reads": "comparisons",
                              "cares_about": "measurable outcomes", "depth_and_angle": "proof and cost",
                              "not_this": "founder anecdotes"}],
                "how_to_pick": "Match the topic: strategy -> Founder; role how-to -> Operator; buying -> CHRO."}
    if '"actionable"' in p:                                   # classify-sections
        m = _re.search(r"FILE: (\S+)", p)
        f = m.group(1) if m else "unknown.md"
        return {"file": f, "sections": [
            {"heading": "Terminology", "summary": "house terms", "actionable": True, "scope": "company", "kind": "rule",
             "why": "changes the word typed",
             "carry": "| Write this | Not this | Why |\n|---|---|---|\n| operators | managers | house term |\n| cohort | class | house term |"},
            {"heading": "Quality Checklist", "summary": "a checklist", "actionable": False, "scope": "company", "kind": "rule",
             "why": "a checklist, not a sentence rule", "carry": ""},
            {"heading": "Social proof", "summary": "numbers", "actionable": True, "scope": "company", "kind": "fact",
             "why": "a fact", "carry": ""},
            {"heading": "Acronyms", "summary": "a list", "actionable": True, "scope": "company", "kind": "reference",
             "why": "a lookup", "carry": ""},
            {"heading": "Sentence Structure", "summary": "vary length", "actionable": True, "scope": "universal", "kind": "rule",
             "why": "true for any company", "carry": "- Vary length: mix short and long"},
            {"heading": "Odd one", "summary": "unknown kind", "actionable": True, "scope": "company", "kind": "weird",
             "why": "the model made up a kind", "carry": "- something"}]}
    if '"findings"' in p:                                     # extract-research-cards
        return {"findings": [
            {"gloss": "nobody validates assessments", "topics": ["validation", "assessments"],
             "verbatim": "44.5% of HR and TA practitioners say no one formally validates their assessments (n=128) [Q9]"},
            {"gloss": "hiring takes four days or more", "topics": ["speed"],
             "verbatim": "78.7% of practitioners take four days or more to shortlist [Q3]"}]}
    if '"subreddits"' in p:                                   # propose-subreddits
        return {"subreddits": [{"name": "r/recruiting", "who": "in-house recruiters", "covers": "the job"},
                               {"name": "humanresources", "who": "HR generalists", "covers": "the job"},
                               {"name": "/r/jobs", "who": "candidates", "covers": "the other side"},
                               {"name": "smallbusiness", "who": "owners who hire themselves", "covers": "the tier below"},
                               {"name": "AskHR", "who": "employees asking HR", "covers": "the adjacent trade"},
                               {"name": "deadsub", "who": "nobody", "covers": "the job"},
                               {"name": "blockedsub", "who": "unknown", "covers": "the other side"}]}
    return None


_VOICE_DOC = """# {brand} Brand Voice & Messaging

This document defines the {brand} brand voice, tone, and messaging framework. Reference this when writing all content to ensure consistency.

## Brand Voice Pillars

### 1. Direct, Backed by Proof
- **What it means**: every claim carries a number from the company's own pages
- **How it sounds**: short sentences, a figure before an adjective
- **Example**: "Every week ends with a decision made on real numbers."
- **Avoid**: vague scale words where a real number exists, stacked adjectives

### 2. Operator's Eye
- **What it means**: written for people who already run things
- **How it sounds**: second person, a decision in every section
- **Example**: "The work is direct."
- **Avoid**: lecture register, definitions without a decision

### 3. Practitioners, Not Lecturers
- **What it means**: the teacher has done the job
- **How it sounds**: named practice, live cases
- **Example**: "Every cohort is taught by practitioners, not lecturers."
- **Avoid**: academic hedging, credentials in place of results

## Tone Guidelines

### General Tone: The Operator Who Teaches
Imagine an experienced operator explaining a decision to a peer. Plain words, a number where one exists, no padding.

### Tone Variations by Content Type
**How-To Guides**: instructive, concrete
- "Start with the number you will decide on."
**Strategy/Advice Content**: direct, experienced
- "Here is what the operators we work with do differently."
**Industry News/Trends**: analytical
- "This shift means a founder needs a bench, not a certificate."
**Product/Feature Content**: plain, honest
- "A cohort is planned in an afternoon."

## Messaging Framework

### Core Brand Messages
#### Message 1: Learn by running the numbers
- **Concept**: education that ends in a decision
- **Key Points**: live cases; real numbers; a room that argues back
- **Usage**: When discussing programmes

### Value Propositions
**For founders**: "Decide faster, with a bench that can hold a room."
**For senior operators**: "Practice the decision before it costs you."

## Writing Style Guidelines
### Sentence Structure
- **Vary length**: short after long · **Active voice preferred**: "We teach by doing" not "Teaching is done by us" · **Average length**: 12-18 words · **Clarity first**: rewrite anything confusing
### Paragraph Structure
- **Length**: 2-4 sentences · **One idea per paragraph** · **Transitions** · **White space**
### Word Choice
- **Concrete**: "cut time-to-hire 55%" not "improve hiring" · **Avoid**: leverage, seamless, robust
### Terminology
**Say This** → **Not That**
- operators → managers (the people who run things)
- cohort → class (a cohort decides together)
- practitioner → faculty (they have done the job)

## Content Formatting
### Headlines — specific, with a number where real; under 60 characters
### Subheadings — descriptive, scannable
### Lists — numbered for steps, bulleted for items
### Calls-to-Action — the exact on-site text: "Apply now", "Book a call"

## Voice Examples
### Excellent {brand} Voice ✅
"We build programmes for people who already run things. Every cohort is taught by practitioners, not lecturers, and every week ends with a decision made on real numbers."

"Nobody leaves with a certificate they cannot explain."
**Why this works**: opens on the reader · a decision, not a definition · active voice · a real practice named · no padding
### Not {brand} Voice ❌
"Our comprehensive, world-class leadership solutions leverage cutting-edge pedagogy to empower tomorrow's leaders. Click here to learn more."
**Why this fails**: (constructed) corporate-speak · no number · generic CTA · AI clichés · no reader named

## Audience Understanding
### Who We Write For
**Primary Audience**: Founders and senior operators — run a company or a function; decide weekly; distrust certificates; short on time; want a bench
**Secondary Audiences**: CHROs: own the budget · Investors: back the founder · Programme alumni: return for the next cohort
### What They Care About
**Top Priorities**: decision speed · the bench · holding a room · cost of a wrong hire · time
**Pain Points**: certificates that mean nothing · lecturers who never ran anything · slow decisions · a thin bench · vendor hype
### How to Serve Them
- **Respect their time**: a decision per section
- **Show the number**: a real figure, sourced
- **Name the practice**: what an operator actually did

## Quality Checklist
- [ ] Voice · [ ] Tone · [ ] Value · [ ] Clarity · [ ] Accuracy · [ ] Examples · [ ] Action · [ ] Messaging · [ ] Terminology · [ ] Empowerment

---
**Remember**: We teach people who already run things to decide better, by running the numbers.
"""

_STYLE_DOC = """# {brand} Style Guide

## Grammar & Mechanics

### Capitalization
- **Headlines & subheadings**: Sentence case
- **Product names**: {brand}, always capitalised (the company name is always capitalized)
- **Industry terms**: skills assessment · time-to-hire · cohort

### Numbers
- Spell out one–nine; use numerals for 10 and above.
- Always numerals for: percentages (5%), money ($500), measurements (5 GB), and stats/lists.
- Large numbers: use commas (1,000+); spell out "million"/"billion".

### Punctuation
- **Oxford comma**: Yes  (apply consistently)
- **Em dashes**: rare; hyphens preferred
- **Quotation marks**: double
- **Ellipses**: three dots, no surrounding spaces, used sparingly. Rare in the blogs.

### Abbreviations & Acronyms
- Spell out on first use, then use the acronym: "Applicant Tracking System (ATS)".
- **Common industry acronyms** (define on first use): ATS, HR
- Latin abbreviations: use "e.g.", "i.e.", "etc." sparingly.

## Word Choice & Usage

### Preferred Terms — "Say This → Not That"
- operators → managers
- {brand} product names as written on the site — confirm with marketing

### Words to Avoid
- Cut filler: "very", "really", "actually".
- No "click here" / "read more".
- No AI-clichés / hype: leverage, seamless.

### Inclusive Language
- Gender-neutral where possible; people-first language.

## Formatting Standards
### Text Formatting
- Bold for genuine emphasis; italics for terms; no underline; no ALL CAPS.
### Lists
- Bulleted for non-sequential items; numbered for steps.
### Links
- Descriptive anchor text.
### Code & Technical Elements
- `inline code` for UI labels.
### Callout Boxes / Asides
- Use sparingly.

## Content Structure
### Article Introduction
- Hook → the reader's problem → the promise (≈150–250 words).
### Section Length
- One idea per section; ~200–300 words.
### Conclusion
- Summarize the value + one clear CTA.

## SEO-Specific Style
### Meta Titles
- ≤ 60 characters, primary keyword near the front.
### Meta Descriptions
- ~150–160 characters.
### URL Slugs
- Short, lowercase, hyphenated.
### Alt Text
- Describe the image.

## Dates & Time
- Format: "Month DD, YYYY".

## Statistics & Data
### Citing Sources
- Cite the source inline and link it.
### Presenting Numbers
- Numerals for scannability.

## Images & Media
### Image Captions
- Brief and specific.
### Screenshots
- Current, legible.
### Charts & Graphs
- Labelled axes and a clear title.

## Brand-Specific Guidelines
### {brand} Product References
- Name the programme exactly as the site does — confirm with marketing.
### Competitor References
- Fair, factual, no disparagement — confirm with marketing.

## Accessibility
### Screen Reader Friendly
- Real heading hierarchy, alt text, descriptive link text.
### Plain Language
- Short sentences; define jargon on first use.

## Voice & Tone Reminders
### Core Voice Characteristics
- Direct, second-person, proof-backed, plain-spoken. (The full voice lives in `brand-voice.md`.)
### Tone Variations
- See `brand-voice.md` (Tone Guidelines).

## Editing Checklist
Before publishing: spelling checked · punctuation consistent · numbers consistent · preferred terminology used · headings hierarchical · sources cited · ready to publish.

## Updates & Maintenance
- Keep the guide current and aligned with `brand-voice.md`.
"""

_FEATURES_DOC = """# {brand} Features & Benefits

This document outlines {brand}'s key features, benefits, and differentiators to inform content creation that drives trial conversions and customer acquisition.

## Core Value Propositions
### 1. **Cohort builder**
- **Feature**: plan a cohort in an afternoon
- **Benefit**: a programme starts this quarter, not next year
- **Conversion Angle**: "Plan the cohort today; run it on real numbers."
### 2. **Live cases**
- **Feature**: decide on real numbers every week
- **Benefit**: the decision is practised before it costs anything
- **Conversion Angle**: "Practice the decision before it costs you."

## Technical Features
### Programmes
- **Cohort builder**: plan a cohort in an afternoon
- **Live cases**: decide on real numbers
### Integrations
- **Slack**: chat inside the cohort

## Integrations & Ecosystem
### Direct Integrations
- **Slack**: chat inside the cohort

## Competitive Differentiators
### vs. Rival One
- **Practitioners, not lecturers** (Rival One uses faculty); fair note: Rival One has a longer alumni network

## Use Cases by Customer Segment
### Founders
- decide faster; build a bench
### Senior operators
- practise the next quarter's decision

## Pricing & Plan Benefits
### Standard Benefits
- pay per seat; 30-day refund

## Key Messaging for Conversions
### Trial Conversion Messages
- "Apply now"
- "Book a call"
### Pain Point Solutions
- **"Slow decisions?"** → "A decision every week, on real numbers"
### Social Proof Elements
- "1,500+ teams"
- "4.7 on G2"

## Common Questions & Objections
### "Can I cancel?"
**Answer**: Yes, any time.

## Content Creation Guidelines
1. Lead with benefits, not features   2. Use specific examples   3. Include proof points
4. Address objections proactively   5. Clear CTAs   6. Emphasize uniqueness   7. Match audience to use case

---
*Note: Update as new features launch or positioning changes. Keep aligned with current homepage/pricing copy.*
"""


def _brand_text(p):
    brand = "Example"
    m = _re.search(r"THE COMPANY: (.+?) —", p) or _re.search(r"for (\S+) \(", p)
    if m:
        brand = m.group(1).strip()
    if "THE SCHEMA TO FILL" in p:                             # assemble-voice
        return _VOICE_DOC.format(brand=brand)
    if "THE OBSERVED ANALYSIS" in p:                          # fill-template (style guide)
        return _STYLE_DOC.format(brand=brand)
    if "THE FACTS POOL" in p:                                 # fill-schema (features)
        return _FEATURES_DOC.format(brand=brand)
    if "## House decisions" in p:                             # assemble-brief: carry the kept material through
        kept = p.split("## What you are given", 1)[-1].split("## Resolving", 1)[0]
        rows = [ln for ln in kept.splitlines() if ln.strip().startswith("|")]
        table = "\n".join(dict.fromkeys(rows)) or "| Write this | Not this | Why |\n|---|---|---|"
        return ("# Writer brief — %s\n\n> What makes %s's writing its own.\n\n## Who is writing\n%s Team, in the first person plural.\n\n"
                "## What we believe\n1. Practitioners, not lecturers.\n\n## Naming %s\nWrite %s, capitalised.\n\n"
                "## How our writing sounds\nDirect. A number before an adjective.\n\n## Words we use\n%s\n\n"
                "## House spelling\ntime-to-hire, skills assessment\n\n## Phrases we never use\n- leverage\n- seamless\n\n"
                "## Competitors\n*(nothing recorded)*\n" % (brand, brand, brand, brand, brand, table))
    if "## The subreddits, already checked" in p:            # write-field-sources
        def names(block):
            out = []
            for ln in block.splitlines():
                mm = _re.match(r"\s{2}(\S+) — ", ln)
                if mm:
                    out.append(mm.group(1))
            return out
        kept = names(p.split("KEPT:", 1)[-1].split("REJECTED:", 1)[0])
        rej = names(p.split("REJECTED:", 1)[-1].split("UNVERIFIED", 1)[0])
        unv = names(p.split("UNVERIFIED", 1)[-1].split("## Write the file", 1)[0])
        rows = ["| %s | the people in it | very active |" % n for n in kept] + ["| %s | unknown | unverified |" % n for n in unv]
        return ("# Field sources — %s\nNiche: test\nVerified: 2026-01-01\n\n## Reddit\nThe planner may ONLY name subreddits from this table.\n\n"
                "| Subreddit | Who is in there | Activity |\n|---|---|---|\n%s\n\nRejected: %s\n\n## Teamblind\nNo filters; a query is all you get.\n\n"
                "## LinkedIn\nNo filters; the prevailing take, not the complaint.\n" % (brand, "\n".join(rows), ", ".join(rej) or "none"))
    return None


# ---- the write phase -----------------------------------------------------------------
# The write phase runs twenty steps over one article, and every prose-shaping prompt returns the
# article (or one block of it) for code to verify. So these stubs READ the prompt and hand back the
# text they were given, unchanged, plus whatever small decision the step asked for. A test that wants
# a step to misbehave wraps llm.json_call with its own reply for that one prompt.
import re as _re


def _between(text, start, stop=None):
    i = text.find(start)
    if i < 0:
        return ""
    i += len(start)
    j = text.find(stop, i) if stop else -1
    return text[i:j] if j >= 0 else text[i:]


def _bullets(block):
    return [ln.strip()[2:].strip() for ln in block.split("\n") if ln.strip().startswith("- ")]


def _numbered(block):
    """'  3. Heading' lines -> [(3, 'Heading')]"""
    out = []
    for ln in block.split("\n"):
        m = _re.match(r"\s*(\d+)\.\s+(.+?)\s*$", ln)
        if m and not ln.strip().startswith(("job:", "JOB:")):
            out.append((int(m.group(1)), m.group(2)))
    return out


def _sections_md(block):
    """'## Heading\n\nprose' chunks -> [(heading, prose)]"""
    out = []
    for chunk in _re.split(r"\n(?=## )", "\n" + block.strip()):
        chunk = chunk.strip()
        if not chunk.startswith("## "):
            continue
        head, _, prose = chunk.partition("\n")
        out.append((head[3:].strip(), prose.strip()))
    return out


def _parse_rendered_article(block):
    """The article as coherence.render / readable.render lay it out -> the reply shape they expect."""
    h1 = ""
    m = _re.search(r"^# (.+)$", block, _re.M)
    if m:
        h1 = m.group(1).strip()
    out = {"h1": h1, "intro": "", "quick_answer": "", "sections": [], "faq": [], "close": ""}
    intro = _between(block, "INTRO:", "\n\n##") if "INTRO:" in block else _between(block, "# " + h1 + "\n", "\n## ")
    if "QUICK ANSWER:" in intro:
        intro, _, qa = intro.partition("QUICK ANSWER:")
        out["quick_answer"] = qa.strip().split("\n\n##")[0].strip()
    out["intro"] = intro.strip()
    for head, prose in _sections_md(block):
        if head.lower().startswith("quick answer"):
            out["quick_answer"] = prose.split("\n\n##")[0].strip()
            continue
        if head.lower().startswith("frequently asked questions"):
            continue
        # a section chunk may carry the FAQ / close marker at its tail
        prose = _re.split(r"\n\n(?:## Frequently asked questions|FREQUENTLY ASKED QUESTIONS|\(the close sits|CLOSE  \()", prose)[0]
        out["sections"].append({"heading": head, "prose": prose.strip()})
    faq_block = _between(block, "Frequently asked questions\n", "(the close sits") or \
        _between(block, "FREQUENTLY ASKED QUESTIONS\n", "CLOSE  (")
    for q, a in _re.findall(r"\*\*(.+?)\*\*\n\n(.*?)(?=\n\n\*\*|\Z)", faq_block.strip(), _re.S):
        out["faq"].append({"question": q.strip(), "answer": a.strip()})
    close = _re.split(r'\(the close sits under the heading "[^"]*"\)\n\n|CLOSE  \(it sits under the heading "[^"]*"\):\n\n', block)
    if len(close) > 1:
        out["close"] = close[-1].strip()
    return out


def stub_write_json(p):
    """None when the prompt is not one of the write phase's; otherwise its reply."""
    if '"keep_table_stakes"' in p:
        return {"keep_questions": _bullets(_between(p, "PEOPLE-ALSO-ASK QUESTIONS:", "RELATED SEARCHES:")),
                "keep_related": _bullets(_between(p, "RELATED SEARCHES:", "TOPICS THE RANKING PAGES SHARE")),
                "keep_table_stakes": _bullets(_between(p, "(the table stakes", "\nRules:"))}
    if '"why_untagged"' in p:
        out = []
        for m in _re.finditer(r"\[index (\d+)\] H3: (.+?)\n((?:  .*\n?)*)", p):
            idx, title, cards = int(m.group(1)), m.group(2), _re.findall(r"- id(\d+) \[", m.group(3))
            if "(off-topic)" in title:
                out.append({"index": idx, "tags": [], "why_untagged": "WRONG WORLD: belongs to another field"})
            else:
                tags_ = [{"tag": "asset-angle", "cards": cards[:1]}]
                if "- T1:" in p:
                    tags_.append({"tag": "common-h2: T1", "cards": cards[:1]})
                out.append({"index": idx, "tags": tags_, "why_untagged": ""})
        return {"h3s": out}
    if '"placements": [{"orphan"' in p:
        n = len(_re.findall(r"^\[index \d+\] .+\| tags:", _between(p, "THE ORPHANS"), _re.M))
        return {"placements": [{"orphan": j, "into": 0} for j in range(n)]}
    if '{"verify": [' in p:
        return {"verify": []}
    if '"supports": true|false' in p:
        return {"supports": True, "quote": "", "note": ""}
    if '"archetype": "<one of the 8 labels>"' in p:
        return {"archetype": "how-to-guide", "why": "steps a reader works through"}
    if "You are finding the OPTIONS of a comparison article" in p:
        return {"entities": [{"name": "Option A", "count": 3}, {"name": "Option B", "count": 3}]}
    if "You are finding the LIST ITEMS of a listicle" in p:
        return {"entities": [{"name": "Item one", "count": 2}, {"name": "Item two", "count": 2},
                             {"name": "Item three", "count": 2}, {"name": "Item four", "count": 2},
                             {"name": "Item five", "count": 2}]}
    if '"yardsticks": [' in p:
        return {"yardsticks": ["pricing", "support quality", "integration effort"]}
    if '"category": "<the kind of thing' in p:
        ents = _bullets(_between(p, "THE OPTIONS:", "THE YARDSTICKS"))
        return {"category": "tools", "keep": [{"name": e, "yardsticks_covered": ["pricing", "support quality"]} for e in ents],
                "dropped": []}
    if '"coverage_note"' in p:
        secs, cur = [], None
        for ln in _between(p, "THE MATERIAL", "\nTHE MAIN RULE").split("\n"):
            m = _re.match(r'\s*H2: "(.+)"', ln)
            if m:
                cur = {"job": "Settle what %s means for the reader and show it." % m.group(1).lower(),
                       "headline": m.group(1), "covers": None, "lead_boxes": [], "h3s": [], "table": None,
                       "list": None, "needs_research": [], "is_item": True}
                secs.append(cur)
                continue
            m = _re.match(r"\s*\[#(\d+)\] (.+?)\s+\(\d+ cards\)", ln)
            if m and cur is not None:
                # the first box opens the section; every later one gets an authored sub-heading, so the
                # "### " rendering paths downstream are exercised
                if cur["lead_boxes"]:
                    cur["h3s"].append({"h3": "Where %s Fits" % m.group(2).strip().title(), "boxes": [int(m.group(1))]})
                else:
                    cur["lead_boxes"].append(int(m.group(1)))
        out = {"coverage_note": "left nothing out", "spine": "The reader learns what the numbers mean and what to do next.",
               "sections": secs, "benched": []}
        if '"item_fields"' in p:
            out["item_fields"], out["dropped_items"] = [], []
        if '"artifact": {' in p:
            out["artifact"] = {"type": "checklist", "contains_boxes": [], "note": "a one-page checklist"}
        return out
    if '"kind": "research" | "result"' in p:
        return {"placements": [], "notes": "nothing earns a place"}
    if '"allocation":' in p:
        n = len(_re.findall(r"^\[(\d+)\] ", _between(p, "THE SECTIONS"), _re.M)) or 1
        return {"allocation": [{"section": i, "share": round(100.0 / n, 2), "why": "even"} for i in range(n)]}
    if '"hunt": true|false' in p:
        return {"sections": [{"n": n, "hunt": n == 1, "why": "stub"} for n, _ in _numbered(_between(p, "THE SECTIONS, in order:"))]}
    if '"seeds": [' in p:
        return {"seeds": ["seed one", "seed two"], "why": "what the evidence says"}
    if '"keyword": "<the phrase, or null>"' in p:
        first = _between(p, "CANDIDATES (keyword | monthly volume | difficulty):\n").strip().split("\n")[0]
        kw = first.split("|")[0].strip()
        return {"keyword": kw, "volume": None, "kd": None, "why": "names what the section delivers"}
    if '"keyword_used"' in p:
        m = _re.search(r"Working heading \(a draft — you are replacing or keeping it\): (.+)", p)
        return {"heading": m.group(1).strip() if m else "Heading", "keyword_used": None, "why": "kept, it already lands"}
    if '"headings": [{"n"' in p:
        heads = _numbered(_between(p, "LOCKED keyword:\n", "\n────"))
        return {"headings": [{"n": n, "heading": h, "changed": False, "why": ""} for n, h in heads], "notes": ""}
    if '{"h1": "<the H1>"' in p:
        m = _re.search(r"- H1 as planned: (.+)", p)
        return {"h1": m.group(1).strip() if m else "The H1", "why": "already carries the primary"}
    if '"keywords_skipped"' in p:
        secs = _sections_md(_between(p, "THE ARTICLE, in order, as written:", "WHAT THE COUNTER ALREADY FOUND"))
        return {"sections": [{"heading": h, "prose": pr} for h, pr in secs], "edits": [],
                "keywords_used": [], "keywords_skipped": []}
    if '"dropped_questions"' in p and '"touch_ups"' in p:
        pages = _between(p, "Pages you may link to.", "\n────")
        urls = _re.findall(r"https?://[^\s)\]>\"']+", pages)
        url = urls[0].rstrip(".,") if urls else ""
        close = ("The numbers only help once they change a decision. Start with the one figure your team argues "
                 "about most. " + ("We built our [product tour](%s) for exactly that first step." % url if url
                                   else "That is where the work starts."))
        return {"h1": _between(p, "- Working H1: ", "\n").strip(),
                "intro": ("Most teams quote a number they never checked. The figure came from a slide, the slide came "
                          "from a vendor, and nobody kept the source. That gap costs real money every quarter. "
                          "This piece settles which numbers hold up and what to do with them."),
                "quick_answer": ("The short version: check the source of every figure you repeat, keep the two that "
                                 "survive, and drop the rest. Most of the numbers in circulation trace back to one "
                                 "old survey. The ones that hold up point the same way, so you can act on them "
                                 "without waiting for better data. Start with the cost figure, because it drives "
                                 "the rest of the budget conversation."),
                "faq": [{"question": "How often should the figures be checked?", "answer": "Once a year is enough for most teams, sooner if a vendor changes its method.", "origin": "researched"},
                        {"question": "Does the size of the team change the answer?", "answer": "Smaller teams feel each figure more, so they should check sooner and act faster.", "origin": "added"}],
                "dropped_questions": [],
                "close_heading": "Where To Take This Next",
                "close": close, "cta_link": url, "touch_ups": []}
    if "Fix ONLY what is listed above" in p and '"close_heading"' in p:
        urls = _re.findall(r"https?://[^\s)\]>\"']+", _between(p, "Pages you may link to.", "\n────"))
        url = urls[0].rstrip(".,") if urls else ""
        return {"close_heading": "Where To Take This Next",
                "close": "Start with the one figure your team argues about most. " +
                         ("Our [product tour](%s) shows that first step." % url if url else "That is where the work starts."),
                "cta_link": url}
    if '"quantities": [{"amount"' in p:
        return {"rules": [], "scales": [], "quantities": []}
    if '"could_not_fix"' in p:
        art = _parse_rendered_article(_between(p, "THE ARTICLE IN FULL:", "\n════") or _between(p, "THE ARTICLE YOU RETURNED, which is the one to correct:", "\n════"))
        return dict(art, changes=[], numbers_changed=[], could_not_fix=[], verdict="honest and safe to publish")
    if '"quick_answer": "<the Quick answer block, rewritten' in p:
        return _parse_rendered_article(_between(p, "\nTHE ARTICLE\n\n", "\n════"))
    if '"ai_overview_on_topic"' in p:
        stakes = [ln.strip()[2:] for ln in _between(p, "LIST ONE", "LIST TWO").split("\n") if ln.strip().startswith("- ")]
        return {"table_stakes": [{"topic": s, "covered": True, "where": "the first section"} for s in stakes],
                "ai_overview_on_topic": True, "ai_overview_subject": "", "ai_overview": []}
    if '"how": "<one short line: shortened' in p or '"swapped":' in p:
        return {"fixes": []}
    if '"longest_kept"' in p:
        return {"prose": _between(p, "THE BLOCK\n\n", "\n\n════").strip(), "moves": [], "longest_kept": ""}
    if '"rule": "<which tell it was' in p:
        return {"prose": _between(p, "THE BLOCK, as written:\n\n", "\n\n────").strip(), "changes": []}
    if '"anchor": "<the exact words' in p:
        for sec in p.split("SECTION: ")[1:]:
            head = sec.split("\n", 1)[0].strip()
            text = _between(sec, "ITS TEXT:\n", "\nPAGES SHORTLISTED")
            urls = _re.findall(r"  - \[[A-Z]+\] (\S+)", sec)
            words = _re.findall(r"[A-Za-z]+", _re.sub(r"\[c[^\]]*\]", "", text.split(".")[0]))
            if urls and len(words) >= 3:
                return {"links": [{"section": head, "anchor": " ".join(words[1:4]), "url": urls[0],
                                   "why": "the page treats this in depth"}], "rejected": []}
        return {"links": [], "rejected": []}
    if '"after_section"' in p:
        return {"pointers": [], "rejected": []}
    if '"anchor_phrase"' in p:
        urls = _re.findall(r"  - \S+ · (\S+)\n", p)
        return {"kept": [{"url": u, "anchor_phrase": None, "why": "primary source"} for u in urls[:2]], "rejected_examples": []}
    if '"keep": [<the place numbers' in p:
        return {"sources": []}
    return None


def stub_write_text(prompt):
    """A body section from the shape the write-body prompt shows: the opening's facts, then each
    sub-heading with its own, every fact tagged. None for any other prompt."""
    if "HOW THIS SECTION IS SHAPED, AND THE ONLY FACTS YOU MAY USE" not in prompt:
        return None
    m = _re.search(r"^Heading: (.+)$", prompt, _re.M)
    head = m.group(1).strip() if m else "Section"
    shape_block = _between(prompt, "- What you may NOT do is use a fact from a different section, or invent one to fill a gap.\n\n", "\n\n════")
    out = ["## " + head, ""]
    para = []

    def flush():
        if para:
            out.append(" ".join(para))
            out.append("")
            para.clear()

    for ln in shape_block.split("\n"):
        m = _re.match(r'SUB-HEADING \(render it exactly, as "### (.+)"\):', ln.strip())
        if m:
            flush()
            out += ["### " + m.group(1), ""]
            continue
        m = _re.match(r"\s+\[c(\d+)\] (.+?)  — source:", ln)
        if m:
            fact = m.group(2).rstrip(".")
            para.append("%s [c%s]. That matters because the budget moves with it." % (fact, m.group(1)))
            if len(para) == 2:
                flush()
    flush()
    if len(out) <= 2:
        out.append("There is little checked evidence here, so this section says only what it can prove and stops.")
    return "\n".join(out).strip()


def stub_write_network():
    """Close the write phase's one door to the network. A fetched page is the card's own text (so a
    number check passes), a link is always alive. Tests that want a dead page or a wrong page set
    _common.FETCH_ONCE / _common.ALIVE themselves."""
    from seo_agent.write import _common
    _common.FETCH_ONCE = lambda url, timeout=15.0: ("Stub page for %s. " % url) * 60
    _common.ALIVE = lambda url: True
    _common.FETCH_GAP = 0.0


# ---- the write phase's inputs, shaped as CONTRACTS.md describes them ----------------------

def write_inputs():
    """(blueprint, research, cards) for one small article: three sections, two sub-sections each, one
    of them off-topic so the tagger has something to drop, eight evidence cards with real numbers."""
    cards = [
        {"id": 1, "gloss": "Average cost per hire is 4,700 dollars", "verbatim": "The average cost per hire was $4,700 in 2023, per the SHRM benchmarking survey.", "source_urls": ["https://www.shrm.org/research/cost-per-hire"], "tag": "evidence", "heading": "Costs", "origin": "web", "protected": True, "relevance": 0.9},
        {"id": 2, "gloss": "Soft costs are 60 percent of the total", "verbatim": "Soft costs make up about 60% of the total cost of a hire.", "source_urls": ["https://www.shrm.org/research/cost-per-hire"], "tag": "evidence", "heading": "Costs", "origin": "web", "protected": False, "relevance": 0.8},
        {"id": 3, "gloss": "Time to fill averages 42 days", "verbatim": "The average time to fill a position is 42 days, according to SHRM's Human Capital Benchmarking report.", "source_urls": ["https://www.shrm.org/research/time-to-fill"], "tag": "evidence", "heading": "Timing", "origin": "web", "protected": True, "relevance": 0.9},
        {"id": 4, "gloss": "Structured interviews double predictive validity", "verbatim": "Structured interviews roughly double the predictive validity of unstructured ones, with validity near 0.51.", "source_urls": ["https://journals.example.org/schmidt-hunter"], "tag": "evidence", "heading": "Method", "origin": "web", "protected": False, "relevance": 0.85},
        {"id": 5, "gloss": "Assessments cut turnover by 65 percent", "verbatim": "Teams using a validated assessment before the interview reported 65% lower first-year turnover.", "source_urls": ["https://research.example.net/turnover-study"], "tag": "evidence", "heading": "Method", "origin": "web", "protected": True, "relevance": 0.8},
        {"id": 6, "gloss": "Our programmes page describes the operator cohort", "verbatim": "Every cohort is taught by practitioners, not lecturers, and every week ends with a decision made on real numbers.", "source_urls": ["https://example.com/programmes"], "internal_link": "https://example.com/programmes", "tag": "ownpage", "heading": "Method", "origin": "index", "protected": False, "relevance": 0.7},
        {"id": 7, "gloss": "Student prize contests reward speed", "verbatim": "University hackathon prizes reward the fastest demo, with 48 hours the usual limit.", "source_urls": ["https://uni.example.edu/hackathon"], "tag": "evidence", "heading": "Off", "origin": "web", "protected": False, "relevance": 0.3},
        {"id": 8, "gloss": "Rival vendor claims 30 percent faster screening", "verbatim": "Rival One says its screening tool cuts time to shortlist by 30%.", "source_urls": ["https://rival-one.com/blog/faster-screening"], "tag": "evidence", "heading": "Timing", "origin": "web", "protected": False, "relevance": 0.6},
    ]
    blueprint = {
        "h1": "What Cost Per Hire Really Includes",
        "keyword_set": {"primary": "cost per hire", "variations": ["hiring cost", "cost of hiring"],
                        "secondaries": ["time to fill", "structured interview"], "in_body": ["recruiting budget"]},
        "sections": [
            {"h2": "The Real Cost Of Filling A Seat", "job": "Price a hire honestly, hard and soft costs together.",
             "target_keyword": "cost per hire", "evidence": [1], "internal_links": [], "external_links": [],
             "h3": [{"h3": "The invoiced half", "evidence": [2], "internal_links": [], "external_links": []},
                    {"h3": "Student contests (off-topic)", "evidence": [7], "internal_links": [], "external_links": []}]},
            {"h2": "How Long The Seat Stays Empty", "job": "Show what the empty weeks cost and how vendors talk about speed.",
             "target_keyword": "time to fill", "evidence": [], "internal_links": [], "external_links": [],
             "h3": [{"h3": "The benchmark", "evidence": [3], "internal_links": [], "external_links": []},
                    {"h3": "What vendors promise", "evidence": [8], "internal_links": [], "external_links": []}]},
            {"h2": "What Actually Predicts A Good Hire", "job": "Separate the methods that predict performance from the ones that feel rigorous.",
             "target_keyword": "structured interview", "evidence": [6], "internal_links": ["https://example.com/programmes"], "external_links": [],
             "h3": [{"h3": "Structured interviews", "evidence": [4], "internal_links": [], "external_links": []},
                    {"h3": "Assessments before the interview", "evidence": [5], "internal_links": [], "external_links": []}]},
        ],
        "faq": [], "orphan_keywords": [],
        "persona": {"name": "Head of Talent", "lens": "owns the hiring budget and the time to fill", "why": "they decide"},
        "format_archetype": "how-to-guide", "word_band": {"min": 1400, "max": 1800},
        "angle_filter": {"kept": 8, "dropped": 0},
    }
    research = {
        "topic": "What cost per hire really includes", "angle": "Lead with what the number leaves out, not the benchmark.",
        "world": {"about": "hiring cost for employers", "not_about": "student contests, candidate coaching"},
        "spine": "Most quoted hiring costs count the invoiced half; the decision-grade number includes the empty seat and the bad hire.",
        "keywords": {"primary": {"keyword": "cost per hire", "volume": 2400, "kd": 32, "intent": "informational",
                                 "split_world": False, "why": "best volume we can win"},
                     "variations": ["hiring cost", "cost of hiring"], "secondary": ["time to fill", "structured interview"],
                     "in_body": ["recruiting budget"], "spokes": []},
        "serp": {"who_ranks": [{"rank": 1, "domain": "shrm.org", "title": "Cost per hire", "url": "https://www.shrm.org/x"}],
                 "featured_snippet": "", "ai_overview": {"text": "Cost per hire is total hiring spend divided by hires; SHRM puts the average near $4,700.", "cites": []},
                 "paa_on": ["What is a good cost per hire?", "How do you calculate cost per hire?"],
                 "paa_off": ["What is the cost of a college application?"],
                 "related_on": ["cost per hire formula", "average cost per hire 2024"], "related_off": ["hackathon prizes"]},
        "winners": {"format": "how-to guide", "common_h2s": ["Formula / how to calculate it", "Industry benchmarks", "Hard vs soft costs"],
                    "drift": ["Candidate-side salary negotiation advice"], "gaps_to_own": ["The cost of the empty seat, priced"]},
        "verdict": ["write it"], "build_spec": {"word_band": {"min": 1400, "max": 1800}, "search_intent": "informational"},
        "cannibalisation": None,
        "persona": {"name": "Head of Talent", "lens": "owns the hiring budget and the time to fill", "why": "they decide"},
        "cost_usd": 0.4,
    }
    return blueprint, research, cards


def plant_write_inputs(chat_id, run_id, keep_research=False):
    """Save the three inputs as the run's artifacts, the way research and the blueprint would have.

    keep_research=True merges the write phase's fields INTO a research.json that is already there
    (existing keys win), so a suite that asserts on the earlier tool's output still sees it."""
    from seo_agent import store
    bp, rs, cards = write_inputs()
    if keep_research:
        have = store.load_artifact(chat_id, run_id, "research.json") or {}
        if isinstance(have, dict):
            merged = dict(rs)
            merged.update(have)
            rs = merged
    store.save_artifact(chat_id, run_id, "blueprint.json", bp)
    store.save_artifact(chat_id, run_id, "research.json", rs)
    store.save_artifact(chat_id, run_id, "cards.json", cards)
    return bp, rs, cards


def plant_brand_files():
    """The brand files the writer reads, small but real-shaped."""
    from seo_agent import store
    store.save_knowledge("brand/company.json", {"brand": "Example", "domain": "example.com", "wordpress_url": "",
                                                "brand_oneliner": "practitioner-led education for operators",
                                                "niche_definition": "", "location_name": "United States",
                                                "language_code": "en", "about": "We teach by doing."})
    store.save_knowledge("brand/writer-brief.md", "# Writer brief\n\nWHO IS WRITING: we, the faculty.\nWHAT WE BELIEVE: decisions beat certificates.\n")
    store.save_knowledge("brand/features.md", "# Features\n\n- Programmes: cohort-based, practitioner-led.\n- The tour: a walk through a live case.\n")
    store.save_knowledge("brand/cta-pages.md", "# Pages a close may link to\n\n- Page: https://example.com/programmes\n  What it is for: the programme list.\n- Page: https://example.com/about\n  What it is for: who we are.\n")
    store.save_knowledge("brand/persona.md", "| Persona | Lens |\n|---|---|\n| Head of Talent | owns the hiring budget |\n")
    store.save_knowledge("brand/writing-examples.md", "We build programmes for people who already run things. Every cohort is taught by practitioners.")
    store.save_knowledge("competitors.json", {"competitors": [{"domain": "rival-one.com", "why": "same programmes"}]})


# ---- the research engine's stubs (run_research / build_blueprint) --------------------------------
# Keyed on the literal output keys of prompts/research/*.md. Several of these prompts ask the model to
# echo what it was handed (card ids, candidate keywords, page text), so the stub reads the prompt and
# answers from it, the way a well-behaved model would. Three stubs deliberately misbehave a little,
# so the code that guards against it is exercised: the harvest returns one quote that is NOT on the
# page, the clusterer leaves one card out and doubles another, and the triage asks for four questions.
import json as _json

FAKE_VERBATIM = "This sentence was never on the page."


def _table_rows(p, marker):
    """First cells of the 'a | b | c' lines that follow `marker` in the prompt, until the table ends."""
    if marker not in p:
        return []
    out = []
    for ln in p.split(marker, 1)[1].splitlines()[1:]:
        if " | " not in ln:
            if out:
                break
            continue
        out.append(ln.split(" | ")[0].strip())
    return out


def _ids_after(p, marker):
    block = p.split(marker, 1)[1] if marker in p else ""
    return [int(m.group(1)) for m in _re.finditer(r"^(\d+): ", block, _re.M)]


def _block_json(p, start, end):
    try:
        return _json.loads(p.split(start, 1)[1].split(end, 1)[0])
    except Exception:
        return {}


def _research_json(p):
    if "WORLD STATEMENT" in p and '"not_about"' in p:
        return {"about": "Education programmes for people who already run companies or functions, as buyers of them.",
                "not_about": "Not about machine-operator training, school operator licences, or academic MBA rankings."}
    if '"head_seeds"' in p:
        m = _re.search(r"Article title \(verbatim\): (.+)", p)
        title = _re.sub(r"\([^)]*\)", "", m.group(1) if m else "topic").strip().lower()
        return {"head_seeds": [title], "sibling_seeds": ["cost per hire"], "hygiene": "nothing ambiguous here"}
    if '"spoke_candidates"' in p:                                              # judge-keywords (before the scorer:
        rows = _table_rows(p, "Numbers per keyword (keyword | volume | KD | intent):")
        if not rows:
            return {"primary": {}}
        return {"primary": {"keyword": rows[0], "volume": 0, "kd": 0, "intent": "informational",
                            "split_world": False, "why": "the highest-volume head that clears the difficulty ceiling"},
                "variations": [],
                "secondary": [{"keyword": k, "volume": 0, "kd": 0, "why": "its own section"} for k in rows[1:3]],
                "spoke_candidates": [{"keyword": k, "volume": 0, "kd": 0, "intent": "commercial", "relevance": 8,
                                      "why": "a companion piece"} for k in rows[3:4]],
                "in_body": ["decision speed"], "notes": "no disagreement"}
    if '"distinctness"' in p:                                                  # score-keywords (the judge prompt
        rows = _table_rows(p, "Candidates (keyword | volume | KD | intent):")   # carries the scorer's keys too)
        return [{"keyword": kw, "relevance": 2 if "history" in kw else 8, "distinctness": 6, "brand_fit": 7,
                 "split_world": False, "reason": "fixture score", "role": "primary" if i == 0 else "secondary"}
                for i, kw in enumerate(rows)]
    if '"winners_common_h2s"' in p:                                            # extract-winners
        return {"format": "how-to guide",
                "gaps_to_own": ["what changes after the programme", "cost per hire benchmarks by company size"],
                "winners_common_h2s": ["what it is", "why it matters", "how to measure it"],
                "winners_drift": []}
    if '"build_spec"' in p:                                                    # assemble
        return {"verdict": ["Play: a modest head, an authority piece", "Beatable — head: two strong incumbents",
                            "Beatable — long-tail: yes, the secondaries are low difficulty",
                            "The opening: nobody covers what changes afterwards"],
                "build_spec": {"word_band": {"min": 1500, "max": 2200},
                               "structure": ["primary in H1", "4-7 H2s", "answer-first sections"],
                               "featured_snippet_target": "a 45-word definition",
                               "primary_sources": ["a government statistics office", "a peer-reviewed survey"],
                               "close": "forward step plus one CTA"}}
    if '"relevant"' in p:                                                      # topic-relevance
        return {"relevant": True, "why": "the people searching this are the buyers in the brand scope"}
    if '"why_changed"' in p:                                                   # topic-angle
        return {"angle": "What actually changes for a leader in the six months after a programme, with the numbers.\n"
                         "Cost per hire and time to decision, benchmarked by company size.",
                "why_changed": "the old angle described the curriculum, not the outcome"}
    if "THE SPINE" in p and '"spine":' in p:                                    # build-spine
        return {"spine": "A programme is worth what changes in the six months after it, and here is how to measure that."}
    if '"researchers"' in p:                                                   # pick-researchers
        return {"researchers": [
            {"role": "The Builder", "focus": "how the measurement is actually done, step by step"},
            {"role": "The Sceptic", "focus": "what it costs, when it fails, who it disadvantages"},
            {"role": "The Evidence One", "focus": "whether it works, and how anyone would know"},
            {"role": "The Practitioner", "focus": "the awkward Monday-morning questions"}]}
    if "outlining a RESEARCH DOSSIER" in p or "OUTLINING A RESEARCH DOSSIER" in p.upper():   # dossier-outline
        n = len(_re.findall(r"^\d+\. \[", p, _re.M)) or 1
        half = max(1, n // 2)
        return {"sections": [{"title": "What the measurement actually costs", "questions": list(range(1, half + 1))},
                             {"title": "Whether it works, and how anyone would know", "questions": list(range(half + 1, n + 1))}]}
    if "--- SECTION TEXT ---" in p:                                            # harvest-dossier
        text = p.split("--- SECTION TEXT ---", 1)[1].split("═══", 1)[0].strip()
        sents = [x.strip() for x in _re.split(r"(?<=[.!?])\s+", text) if len(x.strip()) > 30][:4]
        cards = [{"gloss": "dossier fact %d" % (i + 1), "verbatim": x} for i, x in enumerate(sents)]
        cards.append({"gloss": "a quote the model made up", "verbatim": FAKE_VERBATIM})
        return cards
    if "--- PAGE TEXT ---" in p:                                               # harvest-evidence
        text = p.split("--- PAGE TEXT ---", 1)[1].strip()
        sents = [s.strip() for s in _re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 20][:4]
        cards = [{"gloss": "fact %d from the page" % (i + 1), "verbatim": s} for i, s in enumerate(sents)]
        cards.append({"gloss": "a quote the model made up", "verbatim": FAKE_VERBATIM})
        return cards
    if "COVERAGE JUDGE" in p:
        item = (_re.search(r"^item: (.+)$", p, _re.M) or _re.search(r"item: (.+)", p)).group(1).strip()
        dossier = p.split("--- DOSSIER ---", 1)[1].lower()
        words = [w for w in _re.findall(r"[a-z]{5,}", item.lower())]
        hit = any(w in dossier for w in words)
        quote = _re.search(r'"([^"\n]{20,})"', p.split("--- DOSSIER ---", 1)[1])
        return {"item": item, "type": "x", "verdict": "covered" if hit else "no",
                "reason": "the dossier has it" if hit else "nothing on this",
                "evidence": quote.group(1) if (hit and quote) else ""}
    if '"queries"' in p:                                                       # gap-triage: FOUR, the code caps at 3
        return {"queries": [{"query": "what changes for leaders after an executive programme", "fills": ["what changes after the programme"],
                             "source": "flagged", "why": "the differentiator"},
                            {"query": "cost per hire benchmarks by company size", "fills": ["cost per hire benchmarks by company size"],
                             "source": "flagged", "why": "table stakes"},
                            {"query": "when executive education fails and for whom", "fills": [], "source": "own_find",
                             "why": "the honest side"},
                            {"query": "a fourth question that must be cut", "fills": [], "source": "own_find", "why": "over the cap"}]}
    if "--- SECTIONS (index" in p:                                             # harvest-ownpage: keep every section
        idx = [int(m.group(1)) for m in _re.finditer(r"^\[(\d+)\] ", p.split("--- SECTIONS", 1)[1], _re.M)]
        return [{"index": i, "gloss": "what our page says in section %d" % i} for i in idx]
    if '"lens"' in p:                                                          # pick-persona
        return {"name": "Founder / CEO", "lens": "runs a 50-500 person company and decides on programmes for the bench",
                "why": "the topic is a buying decision"}
    if '{"scores":[' in p:                                                     # score-cards
        rows = []
        for ln in p.split("CARDS", 1)[-1].splitlines():
            m = _re.match(r"^(\d+) \| (\S+) \| (\S+) \| (.*)$", ln.strip())
            if not m:
                continue
            cid, text = int(m.group(1)), m.group(4)
            off = "history" in text.lower()
            rows.append({"id": cid, "relevance": 0 if off else 4, "protected": bool(_re.search(r"\d", text)),
                         "reason": "field history, off the spine" if off else "serves the spine"})
        return {"scores": rows}
    if '"clusters"' in p and "--- CARDS (id: gloss) ---" in p:
        ids = _ids_after(p, "--- CARDS (id: gloss) ---")
        if len(ids) > 3:                                    # misbehave: leave the last out, double the first
            odd = [i for i in ids[:-1] if i % 2] + [ids[0]]
            even = [i for i in ids[:-1] if not i % 2] + [ids[0]]
        else:
            odd, even = [i for i in ids if i % 2], [i for i in ids if not i % 2]
        return {"clusters": [c for c in ({"label": "the numbers and what they mean", "card_ids": odd},
                                         {"label": "how the programmes work", "card_ids": even}) if c["card_ids"]]}
    if '"themes"' in p:
        n = len(_re.findall(r"^\d+: ", p.split("--- PROVISIONAL LABELS", 1)[-1], _re.M))
        return {"themes": [{"label": "theme %d" % i, "member_indices": [i]} for i in range(n)]}
    if "--- CLUSTER CARDS (id: gloss) ---" in p:                              # name-cluster
        ids = _ids_after(p, "--- CLUSTER CARDS (id: gloss) ---")
        h3 = [{"h3": "The first two points", "card_ids": ids[:2]}] if len(ids) >= 4 else []
        return {"h2": "What the numbers say about section %s" % (ids[0] if ids else "?"),
                "job": "gives the reader the measured numbers and what to do with them",
                "h3": h3, "card_ids": ids[2:] if h3 else ids}
    if '"orphans"' in p:
        rows = _table_rows(p, "--- CANDIDATE KEYWORDS (keyword | volume) ---")
        return {"orphans": [{"keyword": rows[0], "volume": 0}] if rows else []}
    if '"order":' in p and "--- H2s (index: label) ---" in p:
        n = len(_re.findall(r"^\d+: ", p.split("--- H2s", 1)[1], _re.M))
        return {"order": list(range(n))[::-1]}
    return None


def _research_conversation_text(p):
    """The three text calls of the research conversation, plus the dossier section write."""
    if "YOUR PERSONA BESIDES BEING A WRITER" in p:                             # ask-question
        n = p.count("You: ")
        return "Question %d: what does this actually cost a team of fifty?" % (n + 1)
    if "What do you type in the search box?" in p:                             # question-to-queries
        return "- cost per hire benchmark 2026\n- recruiting cost breakdown by role\n- agency fee percentage"
    if "You are an expert who can use information effectively" in p:           # answer-question
        return ("The published band runs 15 to 25 percent of first-year salary [1]. A mid-size team "
                "reports a blended figure near $4,700 per hire [2]. Both sources agree the internal "
                "share is the one teams forget to count [1][2].")
    if "CAPTURE THE EVIDENCE, not to" in p:                                    # write-dossier-section
        return ("## What the measurement actually costs\n\n"
                "The published agency band runs 15 to 25 percent of first-year salary [1]. "
                "A blended internal figure near $4,700 per hire is reported for mid-size teams [2]. "
                "Read together, the two sources show the internal share is the one teams forget [1][2].")
    return None


def _research_text(p):
    c = _research_conversation_text(p)
    if c is not None:
        return c
    if "```readlist" in p:                                                     # serp-snapshot, the fixed shape
        extract = _block_json(p, "INPUT (raw SERP extract, JSON):", "DO THIS:")
        urls = [r["url"] for r in (extract.get("top_organic") or []) if r.get("url")][:3]
        paa = extract.get("paa") or []
        kw = extract.get("keyword", "the keyword")
        md = ["### SERP snapshot — %s" % kw, "",
              "**Who ranks:**", "- Established HR publishers and two software vendors' blogs",
              "- Open gap: none of them covers what changes after the programme", "",
              "**Featured snippet:**", "- competitor-1.com holds it (paragraph)", "",
              "**AI Overview** — present-to-a-clean-US-crawler *(volatile: personalized, may not show for every user)*:",
              "- What it covers: defines the topic, then names cost, time and measurement",
              "- Who it cites: competitor-1.com, competitor-2.com — not us → GEO gap", "",
              "**PAA — on-angle (FAQ candidates):**"] + ["- %s" % q for q in paa[:2]] + ["",
              "**PAA — off-angle (excluded):**"] + (["- %s" % q for q in paa[2:]] or ["- none"]) + ["",
              "**Related searches — on-angle:**", "- %s examples" % kw, "",
              "**Related searches — off-angle:**", "- none", "",
              "**Read-list handed to the page-reading step:**", "- the three most readable articles", ""]
        return "\n".join(md) + "\n```readlist\n" + "\n".join(urls) + "\n```\n"
    if 'You are writing the "What the winners cover" section' in p:
        kw = (_re.search(r"article on\n(.+?)\.", p) or _re.search(r"cover — (.+)", p))
        return "\n".join(["### What the winners cover — %s" % (kw.group(1).strip() if kw else "the keyword"), "",
                          "**Confirmed format:**", "- how-to guide with a definitional intro; deep — ~2,000 words", "",
                          "**Common H2s (most competitors have):**", "- what it is", "- why it matters", "- how to measure it", "",
                          "**Where the winners drift:**", "- none", "",
                          "**Gaps we can own:**", "- what changes after the programme",
                          "- cost per hire benchmarks by company size", ""])
    if "Reuse verdict:" in p and "OUR CLOSEST EXISTING PAGES" in p:
        urls = _re.findall(r"^\[\d+\] .*? — (https?://\S+)$", p, _re.M)[:2]
        return ("Reuse verdict: Build from parts\nChosen links: %s\n"
                "Why: two pages hold reusable sections on programmes and outcomes, but neither has the angle."
                % "; ".join(urls))
    return None


# ---- DataForSEO, stubbed at the wire --------------------------------------------------------------
# dfs.post is replaced with a fake that answers in DataForSEO's own response shape, so the real
# parsing code in dfs.py runs over it. Credentials are faked so demo mode stays OFF.

DFS_CALLS = []          # every (endpoint, payload) the fake answered, for assertions


def _kw_universe(seed):
    s = (seed or "").strip().lower()
    base = 700 if "cost" in s else 1900
    return [(s, base, 30, "informational"), (s + " programme", 400, 20, "informational"),
            (s + " cost per hire", 250, 35, "commercial"), (s + " history", 50, 10, "informational"),
            (s + " tools", 500, 70, "commercial"), (s + " jobs", 900, 15, "navigational")]


def _kw_item(kw, vol, kd, intent=None):
    it = {"keyword": kw, "keyword_info": {"search_volume": vol, "competition_level": "LOW", "cpc": 1.2},
          "keyword_properties": {"keyword_difficulty": kd}}
    if intent:
        it["search_intent_info"] = {"main_intent": intent}
    return it


def _serp_items(keyword, depth):
    slug = _re.sub(r"[^a-z0-9]+", "-", keyword.lower()).strip("-")
    items = [{"type": "organic", "rank_group": i + 1, "domain": "competitor-%d.com" % (i + 1),
              "title": "%s guide %d" % (keyword.title(), i + 1),
              "url": "https://competitor-%d.com/%s" % (i + 1, slug)} for i in range(min(depth, 9))]
    items.append({"type": "organic", "rank_group": len(items) + 1, "domain": "example.com",
                  "title": "Programmes", "url": "https://example.com/programmes"})
    items += [{"type": "featured_snippet", "domain": "competitor-1.com",
               "description": "%s is a programme for people who run things." % keyword.capitalize()},
              {"type": "people_also_ask", "items": [{"title": "What is %s?" % keyword},
                                                    {"title": "How much does %s cost" % keyword},
                                                    {"title": "Is %s worth it?" % keyword},
                                                    {"title": "What is %s?" % keyword}]},
              {"type": "ai_overview", "items": [{"text": "%s covers what it is, what it costs and how to measure it." % keyword.capitalize()}],
               "references": [{"domain": "competitor-1.com"}, {"domain": "competitor-2.com"}]},
              {"type": "related_searches", "items": ["%s examples" % keyword, "%s cost" % keyword]}]
    return items


def stub_dfs(balance=12.5):
    """Wire-level fake for the research engine's three endpoints plus the balance."""
    from seo_agent.tools import dfs
    DFS_CALLS.clear()
    dfs._auth = lambda: ("fixture-login", "fixture-password")
    dfs.balance = lambda: balance

    def post(path, payload):
        task = (payload or [{}])[0]
        DFS_CALLS.append((path, task))
        if path.endswith("/keyword_suggestions/live"):
            items = [_kw_item(kw, vol, kd) for kw, vol, kd, _i in _kw_universe(task.get("keyword"))]
        elif path.endswith("/keyword_overview/live"):
            known = {}
            for seed in ("operator education", "cost per hire"):
                for kw, vol, kd, intent in _kw_universe(seed):
                    known[kw] = (vol, kd, intent)
            items = [_kw_item(k, *known.get(k, (150, 25, "informational"))) for k in task.get("keywords") or []]
        elif path.endswith("/serp/google/organic/live/advanced"):
            items = _serp_items(task.get("keyword", ""), int(task.get("depth") or 10))
        else:
            raise RuntimeError("the fixture has no answer for " + path)
        return {"status_code": 20000, "cost": 0.0101,
                "tasks": [{"status_code": 20000, "result": [{"items": items}]}]}
    dfs.post = post


# ---- the web, stubbed -------------------------------------------------------------------------------

WEB_CALLS = []


def stub_web():
    """research.web.fetch answers from the URL alone: a page with a few numbered facts and one
    'history' sentence with a year in it, which the card filter must protect."""
    from seo_agent.research import web

    def fetch(url, tries=3):
        WEB_CALLS.append(url)
        kw = url.rstrip("/").split("/")[-1].replace("-", " ") or "the topic"
        host = url.split("/")[2]
        text = ("According to a 2024 survey by %s, 62%% of teams that adopted %s cut their time to decision. "
                "The history of the field goes back to 1990 and 42 early programmes. "
                "The history of the movement is long and contested. "
                "Most teams measure %s weekly against a fixed baseline.\n\n"
                "Cookie notice: we use cookies." % (host, kw, kw))
        return {"url": url, "title": "%s guide (%s)" % (kw.title(), host), "headings": ["What is %s" % kw, "How it works", "Costs"],
                "text": text, "word_count": len(text.split()), "attempts": 1}
    web.fetch = fetch
