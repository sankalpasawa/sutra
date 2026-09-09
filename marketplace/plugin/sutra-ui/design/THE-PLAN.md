# The plan: everything agreed, in one place

**written**: 2026-09-09 · **status**: agreed, not yet built · **audit**: running, section 8 fills in

The owner's rulings are quoted where he gave them and are not to be re-argued.

---

## 1. Fix what is broken (first, before anything new)

| # | What | Detail |
|---|---|---|
| 1.1 | **Check for changes does nothing** | The button, the action and `/knowledge/refresh` all exist, so it fails silently, which is worse than missing. Click it and watch before guessing. |
| 1.2 | **Import a traffic file does nothing** | Same. And see 1.3: it should not be a button at all. |
| 1.3 | **Traffic import is not a button** | It was built for ONE case: his balance hit minus seven cents mid-build and the brand pack could not run. His words: *"why the fuck was that built? That was only for my use case. We are never gonna export a traffic report from outside and put it in Sutra."* The IMPORTER stays (it is the honest fallback when an account runs dry, and the agent should offer it in chat when that happens). The tab button goes. |
| 1.4 | **Foreign chats, in Sutra's OWN Chats folder** | Corrected by the owner 2026-09-09: they do NOT appear in the agent's list. They appear in **Sutra's main Chats folder** — chats he had from VS Code and elsewhere, showing up in the app's own chat list. He does not want them there either. So the fix is in Sutra's chat listing, not the agent's. |
| 1.5 | **The right-hand panel must never open** | "Dust spaces and connections" renders beside the SEO Writer (his screenshot). Not "should be tidied": it should never appear there at all. |
| 1.6 | **The Tools tab is stale** | Eleven tools are listed, so none are missing, but three have raw names (`Refresh site`, `Import traffic`, `Build assets`) where every other tool has a plain one, and the lead paragraph still says "the seven things the agent can do". |
| 1.7 | **"Improve one of our existing pages" is DELETED** | A starter button in the chat with nothing behind it, written before the reuse check existed. It goes away entirely, not rewired. |
| 1.8 | **The Format column missed the build** | Built and shipped, but the shipped copy reads the format from the RUN. The one-line fix that reads it off the article itself was written after the DMG. |

---

## 2. The two carried over

- ~~The competitor keyword net (the ranked net, s1b).~~ **DROPPED by the owner, 2026-09-09:**
  *"you can skip this competitor keyword thing for sure, remove it, don't include it at all."*
  Not to be raised again.
- **The Format column fix** (1.8 above).

---

## 3. The system prompt must know the state

One file, `seo_agent/prompts/system.md`. Today its setup section says: read the site, index it,
build the brand pack, done, ask what to write. **It never mentions the asset engine or the first-run
questions**, both of which shipped today. So a new company is never offered either.

What he asked for, in his words: *"let's say the user has done only the knowledge base and the next
time he asks 'I want to create a new idea', it should say 'hey look, you've not updated the asset
engine yet'. That's how precise I want it to be."*

The agent is ALREADY told the state every turn (`loop._knowledge_block` reports the catalogue, the
page index, the brand pack, the interview and the asset sheet). What is missing is the brief telling
it what to DO in each case. That is writing, not plumbing.

Cover, at minimum: no site · site but no page index · no brand pack · brand pack but no interview ·
no asset sheet when ideas are asked for · a sheet with nothing left open · no measured traffic ·
DataForSEO below the floor.

---

## 4. The look

One proper pass, not six patches. Same brand, same calm. His asks:

- Section headings **darker and bigger**: The company · The site catalogue · The writer brief ·
  Product facts · Links the close may point at · Competitors
- **Table borders darker**, so a section is visibly a section
- **"Next up" on the Asset ideas tab is not clear.** His words: *"okay next up, oh this is the next
  topic, all of that's not clear."*
- And beyond the list: *"rethink how are you gonna make it look much better, much cleaner, more
  interesting to use."*

---

## 5. Changing prompts from the chat

A way to say "this is not coming out right" and have the agent work out which step owns it.

It reads the prompts, names the step, shows the current wording, and proposes the change. He then
edits it in the Prompts tab. **The agent proposes; the person edits.** An agent that silently
rewrites its own instructions is a thing nobody can debug.

---

## 6. The workspace (the big one)

Five people on one team. One person sets up; nobody else rebuilds a knowledge base.

**His decision: a server, so that clicking save just works for everybody.** Not an export file, not
a shared folder.

### What syncs, and what never leaves the Mac

| Stays local, always | Syncs |
|---|---|
| The site catalogue (12,318 pages) | The competitor list |
| Every page body | The links a close may point at |
| Drafts in progress | The company record |
| Every run folder and its work files | The prompts |
| | The asset ideas and their ticks |
| | Finished articles, when shared |

The rule: **a few thousand rows of text sync. Gigabytes of crawl do not.**

### Every save asks

*"Just me, or the whole workspace?"* on: competitors · CTA links · the company record · prompts ·
the catalogue refresh (worded "make changes") · a finished article ("share").

### Open until section 7 answers it

How the backend actually works. Answered below.

---

## 7. How the sync works, concretely

(Written after his question: *"how does it all get updated? Someone clicks save ten times, someone
creates ten articles, someone changes a prompt. How does it work in the back end?"*)

**A hosted database, free at this size: Supabase.**

- Each person signs in once with an email. That gives every change an author.
- Sutra keeps its local files exactly as now. **Nothing about the local app changes.**
- A shared row is written to the cloud when someone chooses "the workspace", and to disk always.
- Everyone else's Sutra holds a live connection and is **pushed** the change. No polling, no refresh.
- **Last write wins, per row, and the row says who and when.** Two people editing the same prompt is
  the only real collision, and a prompt is one row. Two people ticking different ideas is not a
  collision at all, because they are different rows.
- Offline: changes queue locally and go up when the connection returns. The local file is the truth
  until then, which is the same promise the app already makes.

---

## 8. What the audit found

Five agents walked his 223 scripts and 119 prompts, one layer each. Everything below is a real
finding, verified against both trees. Ordered by what it costs, worst first.

### Tier 1 — live bugs, things silently wrong right now

| # | What | Layer | Fix |
|---|---|---|---|
| 8.1 | **A changed page is never re-read.** `refresh_site` puts sitemap-changed pages through `_fetch_pass`, which calls `fx.get(url)` with no `force`, so it is served from the cache. It re-extracts identical stale HTML and reports "N re-read". Verified by hand. His has conditional GET with ETag/Last-Modified; Sutra's schema dropped both columns. | 00 | small; `force=True` is the stopgap, conditional GET is the real answer |
| 8.2 | **A failed source hunt DELETES cards.** His rule is explicit: a card whose search could not run stays, flagged. Sutra's `else: cut` fires whether or not the hunt could search, and cards past the 250 cap fall into cut having never been fetched. So a DataForSEO outage quietly produces a shorter article that reads as clean. | 04 | ~10 lines |
| 8.3 | **The 80% source-coverage banner is gone.** His prints "SOURCE CHECK INCOMPLETE — only R of W claims judged. Do not publish on this." Sutra records raw counts, no percent, no threshold. The exact failure he built it for (428 unverified claims shipping behind a row of zeros) is invisible again. | 04 | small |
| 8.4 | **`tool_escalation` is captured and thrown away on method 2.** `formats.py` records it into its work file and `_idea_row()` never copies it onto the row. Methods 1 and 3 both set it. So the pool most likely to be calculators is the one arriving marked "no build needed" — the exact fix his format-honesty plan was written for, missing on the exact method it was written to rescue. | 02 | 3 lines |
| 8.5 | **The `voices.md` interview does not close its own gate.** The answers are appended as a prose block; the table cells stay `*(ask)*` forever, and the builder re-reports "4 byline questions" after they were answered. | 01 | small |
| 8.6 | **A malformed reuse reply becomes "brand new"**, the most expensive verdict there is. His retries three times then leaves the row blank for a resume. | 02 | small |
| 8.7 | **`tags.drop()` lost its digit guard** `(?!\d)`, so text glues to decimals ("a validity of.42"). The header still claims "ported verbatim", and Sutra calls it at three sites to his two. | 04 | 1 line |
| 8.8 | **The brand-limitation rule was reverted.** His 2026-09-05 review fix says "never volunteer a limitation, weakness or gap of the brand". Sutra's `write_body.py` still says "name at least one honest limitation". | 04 | 1 line |

### Tier 2 — capability that is simply absent

| # | What | Layer |
|---|---|---|
| 8.9 | **The WordPress bisection.** One record the CMS cannot render takes down its whole content type. His halves the batch until it corners the bad item and keeps the other 99. | 00 |
| 8.10 | **The SPA render rung.** His ladder has 5 rungs; the 5th renders JS pages in a real browser. Sutra records every JS-rendered page as failed, and Sutra already ships the browser. | 00 |
| 8.11 | **A failed gate does not stop anything.** His exits with "the catalogue is NOT trustworthy yet". Sutra reports and carries on, so the brand pack builds on a catalogue that failed its own checks. This is the 400-page-catalogue failure mode, still open. | 00 |
| 8.12 | **No extraction timeout or parallelism.** His runs 4 processes with a hard wall-clock kill, built specifically because trafilatura hangs. We restored trafilatura without the guard. | 00 |
| 8.13 | **The relevance recheck (E7).** The pass he wrote *because* the idea generator is generous one page at a time. Atomic keep/drop, PROTECT at 50+ domains, a 15% sanity cap, propose-by-default with an audit. No equivalent at all. | 02 |
| 8.14 | **Domain validation and candidate enrichment before paying.** Without enrichment his own run missed vervoe, criteriacorp, eskill and testdome. Without validation he paid for two domains that never resolved. | 02 |
| 8.15 | **Soft-404 and duplicate-body kill.** 70 rows in his real run were "Page Not Found" served with a 200. In Sutra those become ideas. | 02 |
| 8.16 | **G2.5 semantic dedup inside the competitor pool.** His measured 97 merges a string key misses. `merge.py` skips same-method pairs on a claim that is false for competitors. | 02 |
| 8.17 | **Format canonicalisation (F0).** He measured 127 distinct labels for 1,202 pages. Without it one strong format reads as three weak ones, which is the question the step exists to answer. | 02 |
| 8.18 | **The gap fill is the weakest evidence in the run.** His re-runs the full four-researcher conversation per gap. Sutra does one keyword search. The holes that matter most get the thinnest answer. | 03 |
| 8.19 | **No dossier health gate.** His refuses under 1,500 words with one retry: "a dud run poisons everything downstream". A 300-word dossier passes silently. | 03 |
| 8.20 | **No offline source recovery.** His recovers a numeric card's real URL by matching against the retrieved snippets and stamps `needs_source` when it cannot. A number can be attributed to a page that never said it. | 03 |
| 8.21 | **The features SEED has no input path.** Sutra reads `_seed/features-seed.md` and calls it authoritative, and nothing can write it: no question, no note, and the API's filename rule rejects any path with a slash. Testlify's whole pricing table is invisible to the crawler, so it is permanently unavailable. | 01 |
| 8.22 | **Voices steps 3 and 4 never asked**, and no author page is checked for life. Byline routing is a machine default nobody agreed to. | 01 |
| 8.23 | **`dropped.md` is never surfaced.** His workflow calls it the first-run check, "the only place a wrong drop shows up". | 01 |
| 8.24 | **The field station lost two of three sources.** Blind carries a verified employer per poster, which nothing else has. | 04 |
| 8.25 | **Four post-shape overrun checks.** The failure they were built for (24 sections on a 2,800-word budget, 57% over) is invisible again. | 04 |

### Tier 3 — thinner, and worth knowing

Archive liveness capped at 5,000 · the traffic ceiling is silent where both files claim it is loud ·
the topic gate judges on a two-line blurb instead of the brand scope that now exists · the coverage
judge reads the cards rather than the dossier · no thin-page fallback for JS pages in research ·
per-section retrieval is unranked · reuse judge reads 3,000 chars where his reads 12,000 · Reddit
comments are 10 flat on 15 posts where his are ~15 expanded threads on 25 · trends consolidates by
word overlap where his uses embeddings, and his own note says recurrence lives at meaning · the
source hunt uses live-advanced search per card where his uses one standard-queue batch (3-5x the
price) · planner timeout 300s where his is 2400s, and a timeout is not retried · no provider
fallback chain · every tunable became a hardcoded constant on both layers 01 and 04 · no per-batch
resume in the competitor study or the style guide · the reviewer-notes loop is gone on persona and
features · CTA pages lost their "every URL is live" guarantee · `research_url` has a reader and no
writer · the one-liner gate became a silent auto-merge.

### My own error, recorded

**I deleted `opinions.md` on a false premise.** I said "nothing ever reads it", having grepped only
Sutra. It IS read, by his `02-asset-engine/1-competitor-study/scripts/step_g0_scope.py:31`, which
folds it into the brand-scope prompt. His plan calls the POV file the thing that "ranks, earns links,
and sets the brand apart". It should be restored, and the decision retaken on the true premise.

### One risk that is Sutra's own, not a port gap

The `{{MEMORY}}` block appended to seven write prompts says user rules "win over any rule above that
they contradict". That is a live override channel that can defeat the fabrication rule, the product
rule and the banned openers. Worth a bound.

### What is genuinely clean

Verified, not assumed. All 22 write-phase steps in his order; all 8 format profiles and 6 craft files
byte-identical; 47 of 50 write prompts identical; 17 of 19 brand prompts identical; the writer
brief's classifier with zero drift; both brand quality gates; every selection cap in layer 01; the
whole keyword chain in layer 03 number for number; the research conversation's shape; the reuse
decision tree; the judge never seeing match scores; and every rewriting pass in the writer keeping
its number-and-citation verification. **"Code counts, the AI judges" holds everywhere in layer 04** —
the faults there are counts deleted, never counts handed to a model.

Sutra also does a long list of things his does not, including the refresh, the browser fallback, the
language-aware typing, the three enforced gates in trends his own scripts never implemented, and a
SEED rule that fixes a real bug in his own code.

## 8b. The owner's verdict on every audit finding (2026-09-09)

**BUILD:** 8.1 refresh never re-reads · 8.2 a failed hunt deletes cards · 8.4 tool_escalation dropped ·
8.7 the digit guard · 8.8 the brand-limitation reversion · 8.9 the WordPress bisection · 8.10 the SPA
render rung · 8.11 a failed gate does not stop · 8.12 no extraction timeout · 8.14 domain validation
and candidate enrichment · 8.15 soft-404s become ideas · 8.16 semantic dedup in the competitor pool ·
8.17 format canonicalisation · 8.18 the gap fill (he called it the most important) · 8.19 the dossier
health gate · 8.20 offline source recovery.

**SKIP, his call:** 8.3 the 80% coverage banner · 8.23 surfacing dropped.md.

**SKIP, second round:**
- 8.6 the garbled reuse reply. His words: *"it is fine to keep it as brand new, what Sutra does is
  fine for me."* Leave it.
- 8.5 and 8.22, the byline questions. His words: *"remove completely everything about the byline
  questions, everything from Sutra for now."* This is a DELETION, not a fix: the two interview
  questions, `voices.md`, the builder, the "Who writes" row, and the byline half of the writer
  brief all come out. He may revisit later.
- 8.3 the 80% coverage banner · 8.23 surfacing dropped.md.

**8.21 the features seed: BUILD, as `pricing.md` (2026-09-09).** His words: *"whenever the user
adds something in features seed we will not call it features seed, we will call it pricing.md."*
A real Knowledge-tab door named "Prices and hidden facts". Editing it rebuilds `features.md` and
nothing else. He explicitly cut the rest of the chain: *"we can skip writing integrity, we can skip
the writer brief as well. So just update the features.md, which is used while writing the final
article. Pricing.md and then features.md. That's it."*

So the chain is deliberately one hop:

    pricing.md  ->  features.md          (BUILD)
    features.md ->  writing-integrity.md (NOT rebuilt, his call)
                ->  writer-brief.md      (NOT rebuilt, his call)

`write/wrapper.py:32` opens `features.md` fresh per article, so the writer picks up new prices with
no rebuild at all. The rebuild reuses the cached `_work/features/facts.json`, so no re-crawl.

**8.13 the relevance recheck: BUILD (2026-09-09).** His words: *"the relevance recheck I approve."*

**`opinions.md`: LEAVE DELETED (2026-09-09).** His words: *"forget opinions.md."* The premise I
deleted it on was false and that is recorded above, but the decision retaken on the true premise is
the same. Not to be raised again.

**Nothing is awaiting a decision. Everything in this document is approved or explicitly skipped.**

**WORKSPACE, decided but ON HOLD (2026-09-09):** everyone can do everything. No owner role, no
permission tiers. His words: *"everyone can change the prompts, let's give that capability to
everyone for now."*

**The shape, his design, not to be re-argued.** Each company brings its OWN Supabase project, rather
than everyone sharing one we host. His reasoning stands on its own: the data then lives in the
company's own account, and each company gets its own free 500 MB.

  Creator, once, about 5 minutes:
    Connections tab -> Create workspace
    Sutra sends him to supabase.com: sign up free, New Project (~2 min to provision)
    Settings -> API gives two values: the Project URL and the service_role key
    He pastes both, types the workspace name
    Sutra creates the tables itself (an empty project has none: this is why the SECRET key
      is needed, and it is the one step his description did not have)
    Sutra packs address + PUBLIC key + workspace name into ONE code, with a copy button
    The service_role key is stored 0600 alongside connections.json and never shared

  Teammate, 20 seconds:
    Connections tab -> Join workspace -> paste the code -> type a name -> done
    Downloads the knowledge pack (~100 MB zipped, ~5 min). Never sees Supabase.

  The accepted trade: whoever holds the code is in, like a shared document link. No email,
  no passwords, no verification codes. His call, and correct at five people.

**Free tier, measured against his real data (2026-09-09):** 500 MB database against under 5 MB of
live rows; 1 GB file storage against ~326 MB raw / ~100 MB zipped; 5 GB egress against ~50 joins a
month. The one real gotcha is that a free project sleeps after 7 days of no activity and the next
person waits about a minute for it to wake. Nothing is lost.

**HELD, 2026-09-09.** His words: *"we can now for now just keep the Supabase on the sideline, on
hold, the workspace and all of that on hold."* Recorded here, not built. Everything above is the
agreed design for whenever it is picked up.

## 9. Order of work

1. **Everything in section 1.** Basic things being broken makes the rest look untrustworthy.
2. **Whatever the audit finds**, triaged worst first.
3. **The system prompt** (section 3), so a new company is walked through properly.
4. **The competitor keyword net** (section 2).
5. **The look** (section 4), one pass.
6. **Prompt changes from the chat** (section 5).
7. **The workspace** (sections 6 and 7), last, with nothing else broken.

## 10. The bar, unchanged

Every engine suite, every node suite, pytest against its known baseline, and the app driven by hand
before anything ships. And one thing not yet done: **a real first-run onboarding on a fresh company**,
which neither of us has ever watched end to end.
