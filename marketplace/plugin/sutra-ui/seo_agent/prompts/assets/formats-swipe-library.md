<!-- Source 1 for method 2's swipe library. Not a prompt: a DATA FILE the code parses.

Copied verbatim on 2026-09-09 from `02-asset-engine/2-model-other-niches/model-other-niches.workflow.md`,
section "The swipe library — proven formats (built from 75 real link-bait pieces)". The original's step A1
says: "Read every row" and "carried forward as-is, with its four columns intact. Nothing rewritten or
summarised; you're copying proven rows, not paraphrasing them."

It lives on disk rather than in a model's head on purpose. Asked to recall "formats that earn links" a
model returns a different list every run, so the pool would drift run to run and two runs of the same
company could not be compared. A table does not drift. The model's own knowledge is still used, but only
as Source 2 (`formats-extra.md`), where it ADDS to this and is clearly marked as the non-deterministic half.

Columns, in order: Format | Real example(s) | Headline template | Why it earns links.
`assets/formats.py: swipe_table()` parses the first markdown table below and nothing else.
-->

# The swipe library — proven formats (built from 75 real link-bait pieces)

This is **Source 1** for Step A. Each row is a format that earned links; pick the shape, not the subject.

| Format | Real example(s) | Headline template | Why it earns links |
|---|---|---|---|
| **Interactive "how it works" explainer / animation** | Animagraffs: *How a Car Engine Works*, *Inside a Jet Engine* | `How [TOPIC] Works` · `Inside a [TOPIC]` | **Reference/visual** — publishers embed & screenshot it |
| **Calculator** | *Compound Interest Calculator*, *Mortgage Calculator*, *How Much Car Can I Afford?* | `[QUESTION]? [Free Calculator]` | **Utility** — cited as "see how much it costs" |
| **Branded index** *(agent knowledge)* | *Big Mac Index*, *Misery Index* | `The [TOPIC] Index` | **Data** — recurring; journalists cite it **by name** |
| **Original research / "We analyzed X"** | Backlinko: *We Analyzed 11.8M Google Search Results* | `We Analyzed [#] [TOPIC]. Here's What We Learned About [TOPIC]` | **Data (original)** — most-cited format there is |
| **Statistics roundup (curated)** | *161 Cybersecurity Statistics & Trends*, *57 NEW AI Statistics* | `# [TOPIC] Statistics and Trends [Updated YEAR]` | **Reference** — writers grab a stat + link the source |
| **Infographic / data-visual** | *Do Looks Matter? (Infographic)*, *How Much Toilet Paper Every Country Uses, Visualized* | `[HOOK]: [STATISTIC]` · `How Much [TOPIC], Visualized` | **Visual + data** — embeddable, can't copy without crediting |
| **Map / geo data viz** | *Map of Africa*; cost-of-living maps *(agent knowledge)* | `Map of [TOPIC]` | **Visual data** — embed magnet |
| **Generator tool** | *Business Name Generator*, *Citation Generator* | `[TOPIC] Generator` | **Utility** — free reusable tool, shareable |
| **Benchmark / grader** *(agent knowledge)* | *HubSpot Website Grader* | `How does your [TOPIC] compare?` | **Utility** — personalised score → shareable |
| **"Best of" award + badge** *(agent knowledge)* | *Best Places to Work* | `Best [GROUP] for [TOPIC]` | **Ego-bait** — winners embed a badge that **links back** |
| **Definitive guide (+ free template)** | *On-Page SEO: The Definitive Guide + FREE Template* | `[TOPIC]: The Definitive Guide + FREE Template (YEAR)` | **Reference** — the canonical link for the topic |
| **"Complete list" / ranking-of-factors listicle** | *Google's 200 Ranking Factors: The Complete List* | `[TOPIC]: The Complete List (YEAR)` | **Reference** — exhaustive, hard to out-do |
| **Rankings (recurring)** | *Law School Rankings*, *College Football Rankings* | `[TOPIC] Rankings` | **Reference** — updated, cited each cycle |
| **Glossary / terms** | *Poker Terminology*, *37 Must-Know Golf Terms* | `[TOPIC] Terms and Definitions` | **Reference** — definitional pages attract citations |
| **Facts listicle** | *125 Interesting Facts About Practically Everything* | `# Interesting Facts About [TOPIC]` | **Reference** — curiosity + easy citation |
| **Checklist / microsite tool** | *GDPR Compliance Checklist*, *Internet Speed Test* | `The [TOPIC] Checklist` · `[TOPIC] Test` | **Utility** — single-purpose free tool |
| **Quiz / typology** | *Body Type Quiz*; *16Personalities (agent knowledge)* | `What is Your [TOPIC]?` | **Novelty** — shareable; B2B angle only |
| **Controversy / opinion** | *How Google Is Killing Independent Sites* | `How [WELL-KNOWN ENTITY] Is [TOPIC]` | **Emotion** — strong opinion drives shares + links |
| **Case study (results)** | *How I Increased Search Traffic 110% in 14 Days* | `[TOPIC] Case Study: How I [OUTCOME] in [X] Days` | **Proof/data** — concrete results get cited |

> **Data-asset shortcut:** when a format needs real numbers (index, research, stats roundup, map), the same
> dataset has a vetted **data-source list** (~100 URLs: data.gov, Pew, FRED, World Bank, Gallup, OECD…) to
> pull public data from. Use it when a format needs evidence the company doesn't already own.

---
