---
type: comparison
reads: workflows/ in `Backlink gets Automated` (the original) · sutra-ui/seo_agent/ (the port)
produces: a step-by-step map of what the original does and what Sutra actually does about it
last_updated: 2026-09-08
---

# The workflow, and what Sutra does about each step

The left column is what the original machine does, in plain English. The right column is what
Sutra does about that step: **built**, **built differently**, or **not built**. Nothing on the
right is a plan; it is what the code does today.

The original has five layers. The first three run **once per company**. The last two run **once
per article**.

| Layer | What it is for | Runs |
|---|---|---|
| 00 Foundation | Learn the company's pages | once |
| 01 Brand context | Learn how they write and what they sell | once |
| 02 Asset engine | Decide what to build that others will link to | once |
| 03 Content machine | Research one topic properly | per article |
| 04 Write phase | Turn that research into a finished article | per article |

**The one-line summary of the difference.** Sutra builds layers 00, 01, 03 and 04 close to
faithfully. It does not build layer 02, and it replaces layer 02's job (deciding what to write
about) with a much simpler topic suggester. Everything else is either the same or better.

---

## Layer 00, Foundation: learn the company's pages

**What this layer is for.** Before anything else, the machine needs to know every page the company
has and what each one is about. Everything later reads this.

| The original workflow | Sutra |
|---|---|
| **Find every page, four independent ways.** It asks the site's own content system for its list, reads every sitemap, asks the public web archive what used to exist, and crawls the links as a last resort. It keeps a note of which source found each page, so a page found by three of them is more trustworthy than one found by one. | **Built, all four.** Same four sources, same provenance note. Sutra adds one thing the original does not have: when a site blocks robots (Testlify blocks everything), it reads the site through a real browser window inside the app. Without that, Testlify could not be read at all. |
| **Settle the list.** The four lists overlap and disagree. It merges them, drops pages that are gone, drops empty template pages, collapses duplicate addresses that are really one page, and drops anything off-site. | **Built.** Same rules, same drop buckets. |
| **Read every page and pull out the text.** It fetches each page politely, keeps the raw copy so it never has to fetch twice, and extracts the body with several extractors, keeping whichever wins. Headings are kept inline so structure survives. | **Built, with one loss.** Sutra has the same extraction ladder minus two of the fallback extractors and the browser-render rung. Measured on the original's own data, those extra rungs won on about 3% of pages. |
| **Pull search traffic.** One bulk call to DataForSEO gets every keyword each page ranks for, so the catalogue knows which pages actually earn traffic. | **Built, but currently off.** The code is the same bulk call. Your DataForSEO balance is below zero, so it skips and says so, and every page shows no traffic. |
| **Check the work and FAIL if it is short.** Coverage gates compare what was found against what was read. The original's rule, in its own words: a short catalogue must never look like success. A failed gate exits with an error. | **Built, and this was wrong until 2026-09-04.** Sutra used to report a failed gate but pass anyway. It shipped a 400-page catalogue of an 11,917-page site with all four checks green. Now URLs found but never read fail the check and say so. Testlify is 11,734 pages with every URL read. |
| **Output**: one row per page with URL, type, title, description, the full text, traffic, intent, and more. | **Same, plus more per row**: the page's own H1, the body length, the cleaned traffic figure, the top keyword and its position, and up to 100 ranking keywords. |

**What Sutra adds that the original does not have:** every page is also turned into "meaning
numbers" (embeddings) so later steps can find the right page by meaning rather than by matching
words. 11,703 pages and 33,039 passages for Testlify.

---

## Layer 01, Brand context: learn how they write and what they sell

**What this layer is for.** Ten builders read the company's own pages and write down how it talks,
what it sells, who it sells to, and what it is allowed to claim. Every article is written from
these files.

**All ten are built in Sutra.** They run as one step called "learn the brand". Below is what each
one does and anything Sutra does differently.

| The original workflow | Sutra |
|---|---|
| **0. Brand facts.** Sets up three files: the company's own numbers, its opinions, and its customer stories. It drafts candidate rows from the site and flags every one for a human to confirm. It never overwrites a file a human has touched. | **Built.** Same three files, same flagging, same never-overwrite rule. On the rebuilt catalogue it drafted 43 numbers and 47 customer stories. |
| **1. Brand voice.** Picks a shortlist of the company's best pages, reads them, and writes down how the company sounds: its pillars, what it does and does not say, with a real quoted example for each. | **Built.** Slightly longer than the original's version and it adds a testable check per pillar. One defect: some HTML symbols leak into the text. |
| **2. Style and mechanics.** The rules of the house style: capitalisation, numbers, dates, how to write a heading, what punctuation is allowed. | **Built.** Longer than the original's, same sections. |
| **3. Product facts.** Reads every product and feature page and writes down exactly what the product does, what it integrates with, and what it is not. This is what stops an article claiming something the product cannot do. | **Built.** 12,833 words against the original's 9,795, because Sutra read 211 product pages. |
| **4. Worked examples.** Picks five real published articles that best show the voice and pastes them in full, annotated with why each is good. The writer imitates these. | **Built.** One bug fixed on 2026-09-07: it was picking the homepage as an example. Now the homepage, pricing pages and anything with scraped navigation in its title are excluded. |
| **5. Reader persona.** Works out who the company writes to, and the depth to write at. One human gate: confirm or edit them. | **Built.** Four personas proposed, flagged for you to confirm. |
| **6. Author voices.** A questionnaire the team fills in with real bylines. The machine never invents an author. | **Built and deliberately left blank.** Sutra ships the unanswered questionnaire, as the original does. It is in your review queue. |
| **7. Writer brief.** Boils the whole brand pack down to the single page a writer actually reads. The original compresses 26,605 words into 1,660. | **Built.** 1,944 words. One section dropped that the original has: a table of who we write to. Worth restoring. |
| **8. Brand cards.** Turns the company's own research and customer results into small cards the article planner can place, each with a real number and a source. | **Built.** Was empty until the catalogue was fixed; now 47 cards. |
| **9. Field sources.** Finds where this company's audience actually argues online and checks each place is real before writing it down. | **Built, but blocked.** Reddit would not answer the checks, so 18 candidates are listed as unverified rather than pretended-verified. |
| Plus three static rule files that ride along: the SEO/AEO/GEO checklist, the writing-integrity contract, and the anti-AI-writing check. | **Built.** Sutra turned the copy step into a real builder. Two small slots in the integrity file are still unfilled. |

**Where you review it:** Knowledge in the app lists all 19 files. Click any one to read it, and
edit it in place. Your edit is the truth from then on.

---

## Layer 02, Asset engine: decide what to build that others will link to

**What this layer is for.** This is the layer that decides *what to make*. It answers one question:
what free thing should we build that other websites will link to on their own? It gathers evidence
three separate ways, turns each into a concrete idea, then checks every idea against pages the
company already has.

What you get at the end is a decision file, not research. For Testlify it is **1,892 ranked ideas**,
each carrying its own proof, a reason ours would beat theirs, and a build-or-reuse verdict.

**NOT BUILT IN SUTRA.** This was a deliberate decision: you said to skip it, because in Sutra the
person picks the topic themselves.

| The original workflow | Sutra |
|---|---|
| **Method 1, competitor study.** Finds which competitor pages earn the most links, and steals the *shape* rather than the topic. One paid call returns 200 domains sharing your keywords; an AI shortlists about 15 and a human approves them. A second paid call pulls each one's top 300 pages by referring domains. Code then drops homepages, dead pages, help subdomains, translated duplicates, job posts and anything with no authority-passing links. An AI labels every survivor by shape (glossary, calculator, data report, how-to, free test), a second pass merges the messy label variants into one vocabulary, and every real page is read in full. A plain group-by then answers the actual question: which shape earns the most links per page. Finally an AI reads each page, names the specific gap in it, and designs the asset we would build instead. | **Not built.** |
| **What Method 1 found for Testlify**, so you can see the scale: 20 approved competitors, 6,652 pages pulled, 3,735 kept after filtering, 2,541 read in full, **42 distinct page shapes measured**. The result is the useful part: a news article averages 136 linking domains, a data report 72, a pillar guide 31, and a product or landing page only 13. That table is the whole argument for what to build. It produced **1,794 ideas**. | **Not built.** Sutra has no equivalent measurement of which page shapes earn links. |
| **Method 2, model other niches.** Imports asset shapes proven in completely unrelated industries and points each at something you can own. It keeps a library of formats, adds more, pre-screens each for whether it could plausibly serve your subject, then adapts one idea per format in a fixed order: topic, then angle, then name, then an honest note about what building it would take. 25 formats survived, **23 ideas**. | **Not built.** |
| **Method 3, study trends.** Reads what the niche is complaining about on Reddit right now, and this is the only method that supplies timeliness. It scrapes public Reddit pages with no key and no login, from subreddits a human approves on real activity rather than subscriber count. An AI tags every post, the tags are grouped by meaning rather than exact wording, and each group is named for the shared pain. Every post lands in exactly one pile, and each pile becomes a full evidence record: the pain, the audience, the emotion, real quotes, and code-counted posts, upvotes and comments. For Testlify: 17 subreddits, **425 posts**, 981 distinct phrases, **180 tensions**, **106 ideas**. | **Not built.** Sutra has a related builder (field sources) that finds *where* the audience argues, but it does not read the arguments or turn them into ideas. |
| **Method 4, merge the pools.** Staples the three lists into one 21-column sheet and merges anything two different methods both found. Duplicates are nominated by meaning at a deliberately loose threshold, because a backlink-derived idea and a Reddit-derived idea are worded very differently, then an AI rules same, combine or separate. A final junk filter proposes drops for nonsense and off-brand ideas, and a human approves the cuts. For Testlify: 1,923 stacked, 11 absorbed as duplicates, 20 dropped as irrelevant, **1,892 final**. | **Not built.** |
| **Method 5, reuse check.** Before building anything, match every idea against the company's own pages. It embeds every page twice, once as its title and once as chunks of its full text, casts 40 candidates per idea, re-ranks to 15, fetches the top 7 real pages and has an AI read them and rule: already have it, improve the existing one, build from parts, or brand new. For Testlify all 1,892 got a verdict: 1,062 build from parts, 769 improve existing, 57 brand new, 4 already have it. | **Built, but moved.** Sutra runs exactly this check, with the same method (Voyage two-vector match, re-rank, then an AI reads the real pages), but once per article inside research rather than across a whole idea pool. The verdict shows in the research brief. |

### What Sutra does instead of this whole layer

You either name the topic yourself, or you ask for suggestions and it does this:

- It works out who your competitors are from what your brand pack says you sell. For Testlify it
  named TestGorilla, Adaface, Vervoe and HireVue on its own, and saved them so it never asks again.
- It picks **one** competitor per run, rotating so you get different ideas each time rather than the
  same safe middle every time.
- It pulls up to 100 keywords that competitor already ranks for, best positions first.
- It checks those against every page you already have, so it will not suggest something you cover.
- It proposes six topics, each sparked by a real keyword the competitor ranks for, with an angle
  and a reason it is yours to write.

### What is actually lost, precisely

Everything downstream in the original reads **one file**, the merged ideas sheet. Four specific
things read it, and each one degrades in Sutra:

1. **Picking the next topic.** The original pulls the next pending row from a queue and reads six
   columns from it, including the target length taken from how long the winning pages actually are.
   Sutra has no queue; you name the topic in a chat.
2. **The keyword seeds.** The original's research starts from the asset row's own title, angle and
   proof URLs, so the keyword work is anchored to a specific piece of evidence rather than a free
   brainstorm. Sutra starts from your topic sentence.
3. **Finding your own pages.** The original reads the reuse check's saved candidate list. **Sutra
   does this better**: it searches all 11,703 of your pages by meaning at write time, rather than
   reading a list saved weeks earlier.
4. **The article format.** The original reads the format column decided by evidence, that is, the
   shape that earns links for this kind of page. Sutra decides format with one AI call at the plan
   step, from the article itself.

### The honest difference

The original decides what to build from **what earns links**. Sutra decides from **what a
competitor ranks for**. Those are different questions with different answers.

The original's is better for link building and it is backed by real measurement: it knows a news
article earns ten times the linking domains of a landing page in your niche, because it counted.
Sutra's is faster, needs no human gate, and costs almost nothing.

If you want one piece of this back, it is **Method 1**. The format table alone (which page shapes
earn links, measured on your actual competitors) would change what Sutra suggests. It needs paid
data and about a week.

---

## Layer 03, Content machine: research one topic properly

**What this layer is for.** Take one chosen topic and research it until a writer could sit down
and write it without opening anything else.

| The original workflow | Sutra |
|---|---|
| **Step 0: Pick the topic and tick the sheet.** A queue of topics with a status column. It pulls the next pending one, one per run, and remembers what has been done so it can run unattended overnight. | **Not built.** Sutra is a chat: you name a topic, or pick one from the six suggestions. There is no queue and no unattended batch. |
| **Step 0b: The world statement.** Before anything, it writes down what this subject IS and IS NOT about. This is the guard against a word that means two things: "hire" is recruiting to us and car rental to someone else. | **Built.** Same step, same purpose, and it is used by every later step. |
| **Step 1: Keywords, search results, and the brief.** Expands seed phrases into a large keyword pool, filters it, prices the survivors with real volume and difficulty, picks one primary keyword with a panel of scorers, then reads the live Google page for it: who ranks, the answer box, the questions people also ask. | **Built, and every call to DataForSEO is identical** in endpoint and settings. One piece is missing: the original also pulls keywords from competitor pages that already rank, which contributed 126 of its 735 keywords. Sutra's pool is narrower for that reason. |
| **Step 1b: Do we already rank for this?** Checks your own site so you do not write a second page competing with your own. Never blocks, just warns. | **Built.** Same rule. |
| **Step 1b: Is this ours to write?** Two AI calls: one decides whether the topic belongs to us at all, the second rewrites the angle based on what actually ranks. | **Built.** Same two calls in the same order. |
| **Step 2: The deep evidence dossier (STORM).** This is the heart of it. It picks four researchers with different jobs, each interviews an expert over several turns, every question shaped by the previous answer. Each question becomes several searches, the pages are read, and the expert answers only from what was retrieved. The result is written up as a long cited document. | **Built as of 2026-09-05, and this was the biggest gap.** Until then Sutra just searched the article's own keywords and read what came back: 7 searches, no questions asked. It now runs the same method as plain code: four mixed researchers, four turns each, three searches per question, then a written dossier. Measured live: 16 questions across 48 searches, a 14,856-word dossier, 483 facts, **256 of them citing more than one source**. The one piece not ported is the shim, a bridge the original needed only because its borrowed library speaks a different protocol. Sutra calls the model directly. |
| **Step 3: The gap check.** Builds a checklist of everything the article must cover (what the winners cover, the gaps we can own, what Google's own answer says), judges the evidence against each item, and fires more research at whatever is missing. | **Built.** Same checklist, same per-item judging, same cap of three follow-up questions. One difference: the original fires a whole new four-researcher round per gap; Sutra fires one more search round. |
| **Step 4: The article blueprint.** Turns hundreds of facts into a plan. It scores every fact against the article's argument and cuts the ones that do not serve it, protecting anything with a real number. Then it groups the survivors into sections, names each section for what its evidence says, orders them, attaches internal links and the FAQ. | **Built, faithfully.** Same thresholds, same protect rule, same "every fact in exactly one section" assertion, same refusal to guess if the scorer crashes. |
| **Step 5: The write-ready bundle.** A cover sheet naming the title, angle, format, target length, the reader, the byline, and ten numbered pointers to everything the writer needs. Plus the plan with all the evidence written into it. | **Built as of 2026-09-05.** Sutra writes the same cover sheet and a research brief document, and adds an evidence trail: all twenty working files named in plain English and openable in the panel, which is the port of the original's numbered proof folder. Two differences: the byline is not picked automatically, and Sutra keeps the facts in a sibling file rather than inlining them into the plan. |
| **Step 6: Log it done and queue the spokes.** Marks the topic complete and adds the smaller related articles it spawned to the queue. | **Half built.** Sutra ranks the spoke keywords but does not turn them into real titles or queue them. |

---

## Layer 04, Write phase: turn the research into a finished article

**What this layer is for.** One bundle in, one finished article out. Four stations: plan it, shape
it, write it, check it.

**Every one of the original's 21 steps is built in Sutra**, except the field station. Here is what
each does.

| The original workflow | Sutra |
|---|---|
| **Gather.** Lifts the research bundle into two piles: the settings (length, format, keyword) and the material to choose from. | **Built.** Two of its three AI calls were dropped because Sutra's research brief already carries those answers as data. |
| **Route the format.** One AI call picks one of eight article shapes. The whole rest of the write phase branches on this. | **Built.** The prompt is byte-identical. |
| **Select.** Tags every sub-heading with the facts that prove it, then kills any heading that does not have enough proof, and re-homes the orphaned facts elsewhere. | **Built, and hardened.** Sutra adds a rule the original only described: a tag is kept only if it names a fact that really belongs to that heading. |
| **Verify sources.** For every claim carrying a number, it fetches the page that claim came from and has an AI judge read the page and rule whether it really says that. A page that will not load is not the same as a wrong claim. | **Built, minus the replacement hunt.** When a source turns out wrong, the original goes and finds a better one. That needs a paid search Sutra does not run, so it reports the claim as unverified instead. |
| **Freeze.** A shape check that stops the whole chain if the plan is malformed. It is a bouncer, not a judge. | **Built.** Same hard and soft flags. |
| **Shape.** Turns the plan into a real structure: every sub-heading becomes a numbered box of facts, and the AI answers with headlines and box numbers only, never prose. | **Built.** All four format routes present. |
| **Enrich.** Where the plan says "this section needs more research", it goes and gets it. | **NOT BUILT.** It needs a paid web search. Sutra records every request and reports them instead. On your cost-per-hire article, nine sections asked for extra research and none of it ran. This is why the benchmark table came out empty. |
| **Place the brand cards.** Puts the company's own research and customer results into the sections where they belong. It never creates a heading. | **Built.** Ran empty until the brand pack was rebuilt; there are 47 cards now. |
| **Allocate words.** Decides how long each section should be. Two passes: importance sets the share, then the evidence acts as a ceiling. Facts can only take words away, never add them. | **Built.** Same two-pass rule. |
| **Section keywords.** Decides which sections deserve their own keyword, then looks those up. Most sections should be no. | **Built, half gated.** The free decision runs; the paid lookup only runs when DataForSEO is connected. |
| **Headings.** Writes the final headings, then reads them all together as a set to catch mixed styles, the same thing named twice, or numbering that jumps. | **Built.** The cross-section pass earned its place on your live run: it renamed a section because it was the worked example and never said so. |
| **Voices from the field.** Searches Reddit, Blind and LinkedIn for what practitioners actually say, probes the titles before spending anything, and writes up the real arguments. | **NOT BUILT.** This is the largest missing piece that needs no paid API. On the original's cost-per-hire article it contributed 1,273 words and shaped two of the best arguments. |
| **Write the body.** One AI call per section. Each call sees only its own facts, so it cannot invent, but sees every other section's brief, so it cannot overlap. | **Built.** The one gap: the field material is passed in empty. |
| **Blend.** Weaves the keywords in naturally. Counts in code, edits, then diffs rather than trusting the AI's own report. | **Built.** Same four phases and guards. |
| **Wrapper.** Writes the intro, the quick answer, the FAQ and the close. | **Built**, plus a coded check that the call-to-action links properly, with one retry. |
| **Coherence.** Reads the whole article as one piece. It makes an inventory first, then edits, because asking a model to work out what to look for *and* find it failed. | **Built.** Fired correctly on your run: it caught the editor inventing two numbers and rejected the edit. |
| **Readable.** Owns density. It deletes facts and spends the words explaining what survives. | **Built.** Same prompt except the five hardcoded examples now come from your own writing-examples file. |
| **Sentence pass.** Owns shape only: same length, same facts, same sections, all checked in code. | **Built.** Same seven checks. On your run it took the average sentence from 18 words to 13. |
| **Slop pass.** Removes the tells of machine writing. The AI proposes; code verifies that no number and no tag changed. | **Built.** |
| **Links.** Places internal links by meaning using the page index, re-ranks on the real page text, judges each one, then does an integrity check: undo every declared insertion and the text must match exactly. | **Built.** All three link pools, the Voyage index, the re-rank, the judge and the integrity diff. |
| **Clean.** Pure code, no AI. Fixes stray characters and spacing. | **Built.** |
| **Assemble.** Puts it together, numbers the sources, and counts the keyword coverage rather than asking the AI whether it did well. | **Built.** One bug fixed 2026-09-04: when no external source survived, it listed the company's own blog posts as the article's sources. An article never cites its own publisher now. |
| Plus review pages: HTML viewers for the plan, the body, the links and the final article. | **Replaced by the app.** The panel is the review surface. |

---

## The short version

**Built and faithful:** the whole site catalogue, all ten brand builders, the research chain
including the four-researcher conversation, the article blueprint, and 21 of the 22 write-phase
steps.

**Built better than the original:** reading a site that blocks robots, finding your own pages by
meaning rather than by title words, and turning the search-results read into data instead of prose.

**Not built, in order of how much it costs you:**

| Missing | What you lose | Needs paid data? |
|---|---|---|
| The asset engine, all of layer 02 | How you decide what to build. The original measured that a news article earns 136 linking domains in your niche against 13 for a landing page. Sutra suggests from one competitor's keywords instead | Yes, Method 1 does |
| Voices from the field | Real practitioner arguments inside the article. It gave the original's cost-per-hire piece 1,273 words and two of its best points | **No** |
| Enrich | Filling the gaps the plan itself asks for. Nine sections asked on your article and none ran, which is why the benchmark table came out empty | Yes |
| The unattended queue | Running a list of topics overnight. Sutra does one at a time, in a chat | No |

**Blocked on money, not on code:** every keyword number, every ranking position and all page
traffic. DataForSEO is at minus seven cents. The code is the same as the original's; it simply
cannot pay to run.

**If you fix one thing next**, make it voices from the field. It needs no paid API, it is the
largest quality gap in the finished article, and it is why a Sutra draft reads correct but generic
next to yours.
