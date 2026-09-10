# Cross-model findings: does the SEO Writer ask sensible questions on every model?

Measured 2026-09-10. `seo_agent/prompts/system.md`, `loop.py` and `registry.py` were read only,
never edited: two other agents were working on them at the same time. Nothing under
`~/.sutra-ui/agents/seo` (the owner's live install) was written to; every run used its own
`mktemp -d` data dir via `SEO_AGENT_DATA`, and those dirs are untouched, so any run below can be
re-inspected.

## Method

Three models, six openings, first two turns each: 18 runs. `seo_agent/llm.py` reads
`SEO_AGENT_MODEL` and passes it to the `claude` CLI as `--model`, so each run drove the real
`claude` binary billed to the subscription, no API key, exactly the path the app uses.

- Models: `claude-haiku-4-5-20251001`, `claude-sonnet-5`, `claude-opus-5`.
- Openings: `hi` / `write me an article` / `write an article about cost per hire` /
  `what can you do?` / `give me some ideas` / (with a knowledge base planted) `write me an
  article`.
- The planted knowledge base (run 6) is a fictional company, "Northlane Metrics", built to the
  same shape as the owner's install (`knowledge/site_index.json`, `knowledge/brand/{company.json,
  features.md, writer-brief.md}`, `knowledge/assets/ideas.json` with 12 rows) but ten pages and
  twelve ideas instead of thousands, so setup was already "done" and the onboarding interview was
  marked answered, to isolate the write-an-article question from the setup side-quest.
- Turn 2 answered whatever turn 1 asked, but bounded for cost: a question about "the website" got
  a domain that cannot resolve (`brief-test-nonexistent-site-9182.invalid`, the reserved `.invalid`
  TLD), so `index_site` fails fast instead of crawling a real site for fifteen minutes. A question
  that would trigger `run_research` or `build_assets` (real, slow, and in the owner's case
  DataForSEO-metered) was left unanswered and logged as skipped, per the brief's own "cut turns,
  not models" instruction. No run got past setup into research or writing; that is a deliberate
  scope cut, not a failure.
- One real bug in the harness itself, not the agent: when a model asked its question in plain
  text rather than through the `ask_user` tool, the run's status went to `done`, not `waiting` (see
  Finding 1). Continuing the conversation then meant starting a new run in the same chat rather
  than calling `loop.resume`. My first pass mis-recorded turn 2 for those runs (it re-read the old,
  finished run instead of the new one); this was caught and every affected file was repaired by
  re-reading the correct run from each data dir's `driver_meta.json`. All 18 result files
  reflect the repaired data.
- No run was killed by the cost timeout (every `killed` flag in the raw results is `false`), so
  every transcript below is complete, not truncated.

Raw results: `driver/results/*.json` and `driver/transcript_dump.txt` in the scratchpad this was
run from (not part of this repo).

## The 18 runs

"Q mechanism" says whether the question that ended the turn went through the `ask_user` tool
(the run pauses, `status: waiting`) or was asked in plain prose with no tool call (the run ends,
`status: done`, indistinguishable to the app from a finished answer).

| # | Model | Opening | Turn 1 Q mechanism | Turn 1 asked | Turn 2 Q mechanism | Turn 2 asked |
|---|---|---|---|---|---|---|
| 1 | haiku | hi | plain text | "What's the website?" | `ask_user` | allow crawler / paste pages |
| 2 | sonnet | hi | plain text | "what's your website?" | `ask_user` | allow / paste / carry on (3 options) |
| 3 | opus | hi | plain text | "What's the website?" | `ask_user` | **caught the fake domain before crawling**; asked for the real one |
| 4 | haiku | write me an article | plain text | "What's the domain?" | plain text | ran `build_page_index` too, then asked allow/paste |
| 5 | sonnet | write me an article | plain text | "What's the website?" | `ask_user` | allow / paste / carry on |
| 6 | opus | write me an article | plain text | "What's the website?" | none (no pause) | ran `index_site` -> `build_page_index` -> `onboard`, paused on an onboarding question instead |
| 7 | haiku | write an article about cost per hire | **`ask_user`** | "What's the website?" (topic never named back) | plain text | allow crawler / paste pages, in prose |
| 8 | sonnet | write an article about cost per hire | plain text | "What's the website?" (topic never named back) | `ask_user` | allow / paste / carry on |
| 9 | opus | write an article about cost per hire | plain text | "What's the website?" **(topic acknowledged: "Cost per hire is a good topic and I've got it noted")** | plain text | caught the fake domain; asked for the real one |
| 10 | haiku | what can you do? | plain text | capability summary, then "What's the website?" | plain text | index_site fails, asks allow/paste in prose |
| 11 | sonnet | what can you do? | plain text | capability summary, then "what's your website?" | `ask_user` | allow / paste / carry on |
| 12 | opus | what can you do? | plain text | capability summary, then "What's the website?" | none (no pause) | ran `index_site` -> `build_page_index` -> `onboard`, paused on an onboarding question instead |
| 13 | haiku | give me some ideas | `ask_user` | "What's the website?" **-- options list is the single garbled entry `example.com`** | plain text | allow crawler / paste pages, in prose |
| 14 | sonnet | give me some ideas | plain text | "what's your website?" | `ask_user` | allow / paste / carry on |
| 15 | opus | give me some ideas | `ask_user` | "What's the website?" **with a second option, "Name a topic instead"** -- and, uniquely for opus, **no DataForSEO disclosure** | `ask_user` | caught the fake domain; also self-corrected: "I should have said that in my first message" |
| 16 | haiku | write me an article (planted KB) | `ask_user` | "Write this one (recommended), or name your own topic?" naming a1000 by id and title | -- | skipped (would trigger real research) |
| 17 | sonnet | write me an article (planted KB) | `ask_user` | "Ready to write a1000, ...?" | -- | skipped (would trigger real research) |
| 18 | opus | write me an article (planted KB) | `ask_user` | "Shall I write a1000, ...?" | -- | skipped (would trigger real research) |

Run 6 (rows 16-18) is the one place all three models agree completely: given an unambiguous
top-ranked idea, all three name it by id and title and ask a single, identical-shaped question
through the proper tool. That is the brief working as intended; it is also the only state in the
table with no interpretive gap for a model to fall into.

## Finding 1 (highest impact, all three models): no instruction to use the `ask_user` tool

Across all 18 runs, **11 of the first questions were asked in plain prose with no tool call**,
which the loop then records as `status: done`, the exact state a finished, un-followed-up answer
gets. Only 7 went through `ask_user` and left the run `status: waiting`. Worse, the same model
does both in the same conversation: haiku's opening 3 run asks the website question through
`ask_user` in turn 1, then asks essentially the same category of question (allow the crawler or
paste pages) in **plain prose** in turn 2, with no tool call at all:

> **Turn 1 (haiku, `ask_user`, properly paused):**
> "What's the website?" -- options: Tell you the domain [recommended]
>
> **Turn 2 (haiku, plain prose, run ends `status: done`):**
> "The site crawl was blocked, so I have 12 pages from what they rank for, but no page text to
> read. This means the brand pack can't be built without it.
>
> Can you allow the crawler on brief-test-nonexistent-site-9182.invalid, or paste in a few pages
> you'd like me to use to learn your voice and house style? Once I have that, I can build the
> pack, then write the article on cost per hire."

Nothing in `system.md` says a question must go through the `ask_user` tool. The closest text,
lines 114-117, covers *when* to ask and how many at once, never *how*:

> "Ask only when the answer changes what happens next AND you cannot work it out yourself. One
> question at a time, with the reason and a recommended option."

The mechanism is only described in `registry.py`'s tool description, which the model sees as one
tool among many in a list, not as a rule. The result: whether a run *waits* for the user, in a way
the surrounding app can detect and show a composer for, or *ends* as if nothing further was
expected, is left to chance per turn, per model.

**Fix:** add a sentence to `system.md`, near the existing "Ask only when..." rule (around line
114), such as: *"Every question to the user goes through the `ask_user` tool, or the show_artifact
/ onboard pause already described. Never end your turn with a bare question in the text: the app
cannot tell that from a finished answer, so the run closes and your question is lost."*

## Finding 2 (opus vs. sonnet, well-evidenced): press on past a blocked crawl, or stop?

When `index_site` hits a site that blocks the crawler, it does not fail outright: it falls back
to a partial catalogue built from search-ranking data (titles, keywords, positions, no page
text) and saves that. What happens next disagrees sharply between models:

**Sonnet stops every time** (5 of 5 times it hit this), with a proper `ask_user` pause:

> "Heads up: the site refused the crawl, so I only got the 12 pages' URLs, titles and keywords
> from search data, not the actual page text. [...] Your call on how to proceed:" -- options: Allow
> the crawler and I'll re-run the site read [recommended] / Paste in a few key pages now / Carry
> on with what we have

**Opus, twice (runs 6 and 12), presses straight on into the next two setup tools before ever
surfacing the question**, running `build_page_index` (which then has nothing to embed and does
not build) and `onboard` (the setup interview), and only pauses once it reaches the interview's
own gate:

> "Two things went wrong, and they have the same cause. [...] I am not running it [the brand pack]
> yet. Two ways to fix that [...]. While you sort that out, the four setup questions are worth
> doing now."
> (then calls `onboard`, and the run's first real pause is the interview's own question, not the
> crawl decision)

Haiku is inconsistent with itself: it stops immediately in run 1, but runs `build_page_index`
first in run 4 before asking, and in runs 7/10/13 it asks in plain prose with no pause at all.

`system.md`'s only nearby rule is the "REFUSED catalogue" rule (lines 107-112), and it does not
apply here: that rule is about a catalogue that failed its own checks and **saved nothing**. This
is a catalogue that **partially saved**, with no page text, and the brief is silent on what to do
next. That silence is exactly why the three models disagree.

**Fix:** add a row to the Knowledge state table (after the "Site catalogue: NOT built" row,
around line 20), such as: *"Site catalogue: built from search data only, crawler blocked (no
page text) -- Say so plainly and STOP: ask whether to allow the crawler, paste a few key pages, or
carry on with thin data. Do not run build_page_index or onboard first: a page index with nothing
to embed and a brand pack fed no text both waste the time you are about to ask for."*

## Finding 3 (opus alone, 3 of 6 openings): sanity-check the domain before crawling

In openings 1, 3 and 5, opus recognised that `brief-test-nonexistent-site-9182.invalid` cannot
resolve (`.invalid` is a reserved, always-dead TLD) **before** calling `index_site`, and asked for
the real domain instead of spending the time:

> "That address won't resolve. `.invalid` is a reserved suffix, reserved precisely so it can
> never point at a real site, so a crawl would come back with nothing and there'd be no pages to
> catalogue. I'm not going to spend an hour proving that. What's the actual domain you want me to
> read?"

Haiku and sonnet never do this, in any of their 10 combined turns that received the fake domain:
both always call `index_site` for real and only report the failure afterward. Opus itself is not
consistent either: in openings 2 and 4 (Finding 2) it does not catch the same domain and crawls it
anyway. So this is not a settled behavior even in the strongest model, it is a coin flip absent an
instruction.

**Fix:** `index_site`'s tool description (`registry.py`) or `system.md` could add a line such as:
*"Before calling index_site, a domain that plainly cannot be real (a placeholder, a reserved TLD
like .invalid/.test/.example, or obvious filler text) is worth one sentence back to the user
asking for the real one, not a crawl attempt."* This is a small, cheap check against a slow, easily
wasted tool call.

## Finding 4 (sonnet vs. opus, opening 3): does the reply acknowledge a topic the user already gave?

The user's message was "write an article about cost per hire": a topic was given, not asked for.

**Opus said so back:**
> "Cost per hire is a good topic and I've got it noted, but I can't research it yet. Knowledge is
> empty: no site catalogue, no brand pack, so there's nothing to write in your voice from."

**Sonnet's reply never uses the words "cost per hire" at all:**
> "Before I can write anything, I need to get your site set up in Knowledge - that hasn't been
> done yet. Also, heads up: DataForSEO isn't connected [...] What's the website?"

**Haiku's `ask_user` call is worse still: the question text is just "What's the website?" with a
single option, "Tell you the domain"** -- the topic is nowhere in the turn at all.

`system.md`'s only instruction here is step 1 of "Writing an article" (line 62): *"Topic. If they
named one, use it."* It says to use it, not to say it was heard. A user who names a topic and gets
a reply that never repeats it back cannot tell whether it registered or is about to be silently
dropped in favor of a suggestion.

**Fix:** append to line 62: *"...use it, and say it back in the same clause you use to explain
what's needed before you can start, so they know it registered."*

## Finding 5 (opus, single run): a rule that already exists was still skipped

`system.md` line 129 is unambiguous: *"If the Knowledge block above says DataForSEO is not
connected [...] say so in your FIRST message of the run [...] Never let the person discover it
from a footnote at the end."* All 17 other runs, across all three models, comply. Opus's run 15
("give me some ideas") does not: its entire first message is "One thing I need before I can
start." with no DataForSEO mention at all. It self-corrects one turn later, unprompted:

> "DataForSEO isn't connected, so any keyword volumes, difficulty scores and ranking positions
> will be demo placeholders, not real. Everything else works as normal. I should have said that
> in my first message."

This is not a missing sentence, the rule is already stated plainly. It is evidence that a single
clear rule, one clause among many bullets under "Rules you do not break," is not followed with
certainty even by the strongest model. Worth a note for whoever owns this file: if this rule
matters enough to call out by name (and lines 129-132 suggest it does, it is one of only four
things named as "first message" material), it may be worth its own short paragraph rather than a
bullet, since bullets compete for attention and this one was the one skipped.

## Finding 6 (haiku, minor defect): a garbled option

Haiku's run 13 ("give me some ideas") calls `ask_user` correctly, but the options array is a
single entry whose label is literally the placeholder text, not a real choice:

> question: "What's the website?" -- options: `example.com`

Worth checking whether `ask_user`'s input schema or description gives an example in a way a
smaller model can mistake for a literal option to echo back (e.g. "e.g. example.com" written
somewhere it could be copied verbatim into the `options` array).

## What was NOT a disagreement, and matters

- **The opening greeting and disclosure.** All three models, on `hi`, gave the DataForSEO
  disclosure and asked for the website in the first message, in that order, every time. No gap to
  fix here.
- **Run 6, the planted knowledge base.** All three models named the exact top idea by id and
  title and asked a properly-paused, single, well-shaped question. This is the control case: when
  the state block gives one unambiguous next action, the models converge. The disagreements above
  all happen in states the brief leaves ambiguous (a blocked crawl, a topic already given, a
  clearly-fake domain), not in states it spells out.
- **All three models append "What's the website?" even to "what can you do?",** a pure
  information request. This is unanimous, not a disagreement, so it is not one of the ranked
  fixes, but it is worth flagging: `system.md`'s knowledge-block tail ("Finish setup first, then
  the article") gives every model the same nudge to fold a capability question into an immediate
  setup prompt. Whether that is the intended read of "what can you do?" is a product call, not
  a model-consistency bug.

## Ranked sentence changes for `system.md`

1. **Add the `ask_user`-is-mandatory sentence** near line 114. Highest impact: it is the only
   finding that is universal (all three models, not a disagreement between them) and it changes
   whether the app can even tell a run is waiting.
2. **Add the blocked-crawl state row** near line 20. Second highest: directly explains the sharpest
   model-vs-model split (opus presses on, sonnet always stops).
3. **Add the domain-sanity-check line**, near `index_site`'s description or the state table.
   Cheap to add, saves a wasted tool call, and is evidence-backed even against opus's own
   inconsistency.
4. **Extend line 62** to say the topic back to the user when one was given.
5. Note (not a sentence add) on line 129's DataForSEO rule: consider promoting it out of the
   bullet list if "first message" compliance matters as much as its current wording implies.
6. Check the `ask_user` tool's schema/description for an example that reads as a literal option
   (haiku's `example.com` echo).
