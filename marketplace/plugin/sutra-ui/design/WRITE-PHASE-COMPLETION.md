# Completing the write phase: one word count, three missing stations, and a Prompts tab

**status**: agreed, not yet built · **written**: 2026-09-09 · **owner's decisions are final below**

Everything here comes from the owner's own words. Where he ruled on something, the ruling is quoted
and is not to be re-litigated by anyone implementing it.

---

## 0. The nine things

| # | What | Why it exists |
|---|---|---|
| 1 | The word count becomes ONE question the person answers | Two steps currently disagree about length |
| 2 | `READABLE_CEILING = 2100` DELETED | A hardcoded cap that ignores the competitors |
| 3 | `WORDS_PER_FACT = 110` used by write-body AND readable | One belief, applied in both places |
| 4 | 234 lines of the owner's own prompt edits pulled in | Sutra is running week-old copies of his craft |
| 5 | Enrich actually searches | Nine sections asked and got a note |
| 6 | The replacement-source hunt actually hunts | A dead source is reported, not replaced |
| 7 | Voices from the field, built | 1,273 words on his own article. Free |
| 8 | Reddit fixed, proven working before it ships | It blocks 7, and left 18 subreddits unverified |
| 9 | A Prompts tab | His craft should not need a developer |

---

## 1. The word count: one question, one number, everywhere

### The bug, exactly

Today the length is decided **twice, by two steps that never speak**:

```
research      band from the pages that RANK        e.g. 2,400-3,000
allocate      midpoint 2,700, shrunk 10% -> 2,430  split across sections by %
write-body    per-section target, "stay near it"
blend         counted against the band
readable      target = min(2100, current)          <-- IGNORES THE BAND ENTIRELY
              keep = target / 110 facts
```

`READABLE_CEILING = 2100` and `READABLE_WORDS_PER_FACT = 110` are in `write/_common.py`. Readable
never reads the band. So competitors at 3,200 words and competitors at 1,400 words both produce an
article cut to 2,100. That is the over-concision the owner has been feeling.

### The fix

**ONE question, asked once per article.** The owner: *"obviously the word count should happen like
stop should happen every time."* And: *"earlier we removed all the questions in between so this is
just going to be the only question."*

So it is the ONLY stop of its kind in a run, and it doubles as the go-ahead for the research
conversation, which begins the moment it is answered.

Where: at the end of the keyword work, once the band exists, BEFORE the research conversation. That
is the last cheap moment; the four researchers are the longest, most expensive part of a run.

What the person sees:

```
The pages ranking for "cost per hire" run 2,400 to 3,000 words. The average is 2,700.

I will write to 2,700 words, and the research team will take about fifteen minutes.

   [ Yes, 2,700 ]        or type a number
```

### THE PART TO BE CAREFUL WITH

The owner flagged this himself: *"you are not going to take the input which is there from the
DataForSEO output file, you are going to take it from what the user has input. So you need to build
those proper placeholders and all of that very properly, like also the links very properly."*

He is right, and this is where a sloppy implementation shows up three steps later as an article of
the wrong length with no obvious cause.

**The rule: after the answer, the person's number is the ONLY source of truth for length.** It is
written into `research.json`'s build spec, replacing the computed band, with the original band kept
beside it under a different key for the record. Every downstream reader takes the person's number.

Every place that touches length, and what changes:

| Where | Today | After |
|---|---|---|
| `research` build_spec.word_band | computed from the ranking pages | the PERSON'S number, with `word_band_measured` kept beside it |
| `allocate_words` base | midpoint of band x 0.90 | the person's number x 0.90 (the shrink stays: every real run overshot) |
| `structure-template.md` `{{WORD_BUDGET}}` | from the band | from the person's number |
| `write-body.md` `{{WORD_TARGET}}` | per-section, from allocate | unchanged mechanism, new source |
| `blend.md` `{{LENGTH}}` | the band | the person's number |
| `readable.py` target | `min(2100, current)` | **the person's number.** No cap |
| `readable.md` `{{TARGET_WORDS}}` | that capped number | the person's number |
| `inline-links.md` `{{WORDS}}` | the article length | the person's number |
| facts kept | `target / 110` | `target / 110`, so the fact count now FOLLOWS the length |

**`READABLE_CEILING` is deleted from the codebase.** The owner: *"should go away completely, not
some safety limit and shit."* Do not leave it as a guard, a max, or a comment. Delete it.

**`WORDS_PER_FACT = 110` moves to a shared constant** and is used by `write_body` as well as
`readable`. The owner: *"just this should be there in both write body and that readable."* Rename it
so it no longer reads as readable's private setting.

### Where the stop is implemented

**Not a tool.** A tool is something the model chooses to call, and a question the person must be
asked cannot be the model's decision. It uses `loop._wait(kind="question")`, the same mechanism as
the topic list, the setup interview and the two asset gates. The research tool returns
`{"ask_words": {...}}`, the loop stops, the answer is written into the run's state, and research
resumes and runs the conversation.

Nothing in the Prompts tab concerns the word count. The owner: *"there is not going to be anything
in the prompt step about the word count."*

---

## 2. The owner's own prompts come back

Diffed `04-write-phase/prompts` against Sutra's. **20 prompts differ. 234 lines of his writing are
missing.** His edits are dated 5 September; Sutra has older copies.

Biggest gaps: `readable.md` **-91 lines**, `wrapper.md` **-40**, `write-heading.md` **-25**,
`sentence-pass.md` **-18**, `write-body.md` **-16**.

What is missing from `readable.md` alone, and every one of these is a deliberate rule:

- **PROFESSIONAL, NOT CHATTY.** Bans "here's the thing", "real talk", slang, jokey fragments. Sutra
  still carries the chatty example AS ITS MODEL, which is the opposite of what he wants.
- **PUT THE BASICS FIRST.** A definition comes before anything that assumes it.
- **CHECK EVERY SECTION AGAINST THE HEADLINE'S PROMISE**, far stronger than Sutra's two lines, and
  ending "off-promise sections are the single loudest complaint reviewers make. Be ruthless here."
- **CONNECT THE SECTIONS.** Absent from Sutra entirely.

**Ten more of his prompts have no copy in Sutra at all**, and they are exactly the three stations we
are now building: `field-plan`, `field-probe`, `field-write`, `field-block` (voices),
`plan-queries`, `search-urls` (enrich), `source-queries` (replacement sources), plus
`extract-cards`, `extract-winners`, `extract-word-band`.

**Rule for pulling them in:** the differences are BOTH his new writing and the port's own token
renaming. Take his content; keep Sutra's `{{TOKEN}}` names where they differ, because the code fills
those. Every prompt must still render with no unfilled token, and there is already a test that
asserts exactly that.

---

## 3. Enrich actually searches

Today `enrich.py` records every needs-research marker as "research that did not happen" and writes
it where the writer can see it. The owner: *"why the hell does it not do that? It got to do that.
Who cares about every marker as research that did not happen. No, we don't want that."*

He is right. A note does not write a section.

**Build it as the original does:** plan queries per marker (`plan-queries.md`), search
(`search-urls.md`), fetch the pages, extract new cards with ids from 9001.

**Nothing new is needed underneath.** The research layer already plans queries, searches, fetches
through the browser-assisted fetcher, and extracts cards. This is wiring an existing capability to
the enrich step, plus the owner's two prompts.

**It must log live**, one line per thing as it happens, like every other step now does.

---

## 4. The replacement-source hunt

`verify_sources` already classifies every card four ways: kept-ok · unloadable-kept · needs-source ·
cut. Today a `needs-source` card is reported. In the original, it goes and finds a replacement
(`source-queries.md`).

Same machinery as enrich. Build it.

---

## 5. Voices from the field

**Not ported at all.** Confirmed: no `field*` prompt in Sutra, no field module.

The original reads where practitioners argue in public and weaves real arguments into the article.
On the owner's own cost-per-hire piece it contributed **1,273 words**. It needs no paid API.

Build it exactly as the original does, from his four prompts: `field-plan` (what to look for),
`field-probe` (go and read), `field-write` (turn it into prose), `field-block` (place it).

Where it sits in the run: the original runs it as a station in the writer. Read
`04-write-phase/write-phase-architecture.md` and place it exactly where the original places it.

---

## 6. Reddit, fixed and PROVEN before it ships

Reddit refused every request from this machine on 2026-09-09, which is why 18 subreddits are marked
unverified and why voices from the field would find nothing.

`brand/field_sources.py` requests `old.reddit.com/r/<sub>/search?...` with a `SutraSEO/1.0`
user agent and reads HTML.

**Diagnose first, then fix.** Known things to try, in order of likely success: the public `.json`
endpoints rather than scraping HTML; `www.reddit.com` rather than `old.reddit.com`; a real browser
user agent; and the browser-assisted fetcher Sutra already has for bot-walled sites
(`tools/_browser.py`), which is exactly what it was built for.

**Do not ship a fix you have not seen return real posts.** The owner: *"fix the reddit part of it
if you see that it's not actually giving out anything. You should fix it right now and then only
see it's working and then push it."*

**And keep the honesty rule that is already there:** a rate-limited Reddit serves a login page with
a success code. That is recorded as "unknown", never as "empty". Whatever the new path is, it keeps
that distinction.

---

## 7. The Prompts tab

A new tab. The owner's craft should not need a developer.

**At the top, a simple flow.** A phrase per step, not a sentence. Every step in it, including the
ones being built in this release, because by then they all run. Nothing is marked "not running":
the owner rejected that outright.

**The format rules come FIRST, before the architect**, because that is where they belong. They are
not part of the architect; they are what it obeys. Eight archetypes, 270-340 lines each, and they
decide what a section must contain. They are the highest-leverage thing he can edit.

**Below it, the prompts as a scrollable list.** Not filling the screen. Click one, it opens, edit
it, save, and it applies to the very next article. It opens showing what it currently says, so he
edits rather than starts from nothing.

**Which prompts:** the eight format rulebooks · write-body · blend · coherence · readable ·
sentence-pass · wrapper.
**Deliberately not:** slop, links, clean. The owner named these as the ones to skip.

**Nothing about the word count is in this tab.**

**Editing changes Sutra only.** The owner: *"it only changes the Sutra app, forget about SEO by
Devansh."* Never write into his folder. A Reset control puts a prompt back to what shipped.

**Where an edited prompt lives:** under the data dir beside knowledge, never in the app bundle,
which is replaced on every update. An edited copy overrides the shipped one at load time; deleting
it restores the original.

---

## 8. A Format column in the Library

So he can see what shape each article was written to. The archetype is already decided at route and
already in the plan.

---

## 9. Order of work, and who does what

Everything here is either a new file or a file with one clear owner. The two shared core files,
`loop.py` and `registry.py`, are the lead's alone, because a bad edit there breaks the app.

1. **Reddit** first, because voices from the field is worthless without it and it is the only item
   whose feasibility is unproven.
2. **The prompts restored**, because it is his own writing and it changes no code.
3. **The word count**, because it is the bug he can feel.
4. **Enrich, replacement sources, voices** in parallel; they share the search-and-extract path.
5. **The Prompts tab** and the Library format column.
6. Full gate, the app driven by hand, DMG.

## 10. The bar

Every suite. The node suites. pytest against the known 29. The app driven in a real browser. And
for Reddit specifically: real posts on screen, or it does not ship.
