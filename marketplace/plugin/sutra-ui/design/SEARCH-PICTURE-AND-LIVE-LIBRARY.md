# The search picture, the live Library, and the credit pre-flight

**status**: proposed, not built · **written**: 2026-09-09

Five things the owner asked for, and what is already true about each. Three of his five questions
were "does this exist", and all three had a real answer in the code, so those are settled first.

---

## A. What already exists (checked, not remembered)

### A1. Spokes are computed, filtered, stored — and NOTHING acts on them

`research/keywords.py::_rank_spokes` ranks spoke candidates, `research/_common.py` sets
`SPOKE_MIN_RELEVANCE = 3` (a hard floor, 0-2 is off-cluster and dropped) and `MAX_SPOKES = 3`.
`tools/run_research.py:270` writes the top three into `keywords.json`. `research/render.py:32` shows
them in the evidence trail.

Then nothing. No step reads them. `HISTORY.md:107` says so outright: "spoke minting" was left out
because "topics come from the chat, not a CSV".

**That reason is now stale.** The asset engine exists, and a spoke IS an idea: a related keyword,
scored, filtered, with volume and difficulty attached. The right move is not to delete spokes but
to give them the home they never had: `merge.py` gains a fourth, cheap source, and spokes arrive on
the sheet as ideas with `method: ["spoke"]`. They cost nothing extra; they are already paid for by
the research run.

Ranked last of the work below, because it is small and nothing breaks without it.

### A2. Common headings, gaps, PAA and related searches ARE load-bearing

They are not shown-and-forgotten. `write/plan_select.py` is built on them:

- `TAG_KINDS = ("gap", "common-h2", "paa", "related")` and `_ID_PREFIX = {"gap": "G",
  "common-h2": "T", "paa": "Q", "related": "R"}`
- every H3 in the plan is tagged against one of those four **by minted id**, so a finished section
  can be traced to the gap or the question it exists to serve
- `winners_drift` is the avoid-list: what the winners cover that this article should NOT
- `write/wrapper.py:109` passes the PAA pool into the writer itself

So the four lists reach the article. They are the skeleton of the plan.

### A3. The gather step exists, and it DOES refine them

`write/gather.py` is planner step 1. Its docstring: one model call, `vet-lists.md`, "which keeps
only the People-Also-Ask questions, related searches and table-stakes topics a reader of THIS
article would care about". `_vet_kept` matches the keep-list back against the originals verbatim,
dedupes, and **never wipes a list to zero**.

So the owner's memory is right: there is a gather step and the PAA are filtered there.

**But it happens LATE.** Gather runs in the write phase, after the blueprint is approved. The raw
lists exist much earlier, at research time. That is the whole reason the screen he wants does not
exist: the refined version is downstream of the moment he wants to look.

---

## B. The search picture (the screen he asked for)

> **SUPERSEDED, 2026-09-09.** Section B below argued for writing this at the end of research step
> 11, from the RAW lists. The owner then changed it: "the moment they get filtered and all of that,
> we have all the clean things there... maybe along with the architect." So it is written at the end
> of the GATHER step, from the VETTED lists, and appears alongside the plan. Everything below about
> raw-versus-filtered is kept only as the record of a decision that was reversed.
>
> The cost of that reversal, and it is real: the picture does not exist until the write phase
> starts, so it sits greyed through the whole research phase, which is the longest part of a run and
> exactly the window he said he wanted to be reading it in. Accepted knowingly: the vetted set is
> the honest one, and building it twice would mean two model calls disagreeing about the same list.

### Where it goes, and why not where he guessed

He asked for it "before the research dossier". That is right, and the reason is stronger than
convenience: everything in it is decided by **step 11, the topic gate**, and everything after step
11 is expensive. The researchers (step 14) are the longest, costliest part of a run. Showing the
search picture immediately after the gate is the last cheap moment.

So: a new artifact written at the end of step 11, before step 14.

### What it contains

Pure assembly from files that already exist. Nothing new is computed, nothing is re-decided.

| Section | Lifted from |
|---|---|
| The keyword and its numbers | `keywords.json` (primary, variations, secondaries) |
| Who ranks now | `snapshot.json` |
| What they all cover | `winners.json` common H2s |
| What none of them cover | `winners.json` gaps |
| What the winners cover that we should NOT | `winners.json` drift |
| People also ask | `snapshot.json` |
| Related searches | `snapshot.json` |
| Who this is for | `persona.json` (his ask) |
| The verdict, and the angle | `topic-gate.json` |
| Spokes, once A1 lands | `keywords.json` |

Rendered by `research/render.py`, which already does exactly this job for the research brief, so it
gains one function and no new mechanism.

**Raw or vetted?** Raw, and it must SAY so. The vetting call belongs to gather and moving it earlier
would either duplicate a model call or move it away from the step that owns it. The screen carries
one line: these are all the questions the search results raise; the plan step keeps the ones this
article should answer. A person seeing 22 PAA questions and later 9 in the article must be able to
see why, or it reads as things going missing.

### It does NOT stop the run

The owner was explicit. So it is **not** a `show_artifact` checkpoint. It is written, announced in
the run log with a link, and the run carries straight on into the researchers. He can open it while
they work, or afterwards, or never.

This is a new shape for this codebase: today an artifact is either a checkpoint that stops, or a
file only reachable through the evidence trail. This is a third thing, an artifact that is
announced but not waited on. Worth naming as a pattern because C below needs the same thing.

---

## C. The live Library (the biggest change, and the one to be careful with)

### What the Library is today

`store.library_save` runs ONCE, from `loop.save_to_library`, when a draft is approved or published.
A Library item is a folder holding `draft.md`, `meta.json`, and copies of `research.json`,
`blueprint.json`, `topics.json`. The screen shows title, status, words, keyword, age, and Open.

So the Library means "finished articles".

### What he is asking for

The row appears when the article STARTS, and fills in as the run produces things. Every milestone
clickable from there.

### The design decision that makes this cheap

**Do not copy files into the Library as they are made. Point at the run.**

A run already writes every artifact to `chats/<chat>/runs/<run>/artifacts/`, and
`research/render.py::trail()` already walks 20 named work files and returns a labelled list of what
exists. The Library item needs `chat_id` and `run_id`, which `library_save` already stores.

So a live Library row is: create the item at run start with `status: "writing"`, and have the screen
render `trail()` for that run. Nothing is copied twice, nothing can drift from the run, and a
crashed run leaves a row that honestly shows how far it got.

The final `library_save` then UPDATES that row rather than creating one. Which means
`store.library_save` needs an "already exists" path, and its id (`<date>-<slug>`) is minted from the
title, which is not known at run start. So the id has to become the run's own id, with the title
filled in later. **That is the one real migration risk in this whole document**, because existing
items have date-slug ids and the front end passes ids around.

Safe route: keep date-slug for finished items, add `run:<chat>:<run>` ids for in-progress ones, and
have the item merge into its date-slug identity at save time, keeping both reachable. Ugly but
reversible, and no existing id changes.

### What the screen becomes

The Library gains a state per row: **writing · ready to read · published**. An in-progress row shows
its milestones as a compact strip, each one clickable into the panel:

`researched · planned · written · edited` and, once B lands, `the search picture`.

Greyed until they exist. This is `agStagesHtml`'s job in the chat, and the row version is a smaller
form of the same thing, so the vocabulary is already there.

### The honest cost

The Library stops meaning "finished work". A person who opens it mid-run sees a half-thing. That is
what he asked for and it is defensible, but the copy has to carry it: the states must be obvious at
a glance or the tab reads as full of broken articles.

---

## D. The DataForSEO pre-flight (the smallest change, the biggest daily win)

### What happens today

`tools/index_site.py` guards `serp_advanced` against the balance floor before it fires. That guard
exists because a run once nearly fired 48 doomed calls. `learn_brand` refuses up front when there is
no measured traffic, naming both ways out.

But an ARTICLE run has no such guard. It starts, does steps 1-4 for free, reaches step 5, cannot
pay, marks every number a placeholder, and carries on for another twenty minutes producing an
article built on estimates. The owner's words: "it is pointless, a very bad experience".

### Where the check goes

Three places, all cheap, all reading one balance:

1. **Before the run starts.** `run_research` pre-flights the balance the way `learn_brand`
   pre-flights traffic, and refuses with a plain message naming what it needs. Same shape, same
   voice, one more caller.
2. **On the button.** The Asset ideas tab's "Write this one" and the composer both know. Disabled
   is wrong (he may want a placeholder run deliberately); a quiet line saying the numbers will be
   estimates, with the button still live, is right.
3. **In Connections**, where the balance already belongs, as a number rather than a tick.

**One thing to get right:** the check must be cached, not fired per keystroke. The balance endpoint
is itself an API call, and checking it on every render would be its own bug. Once per app start and
after any run that spends, held in the health payload that already exists.

**And it must fail OPEN.** If the balance check itself errors, the run proceeds. A network blip must
not block an article; the paid step errors loudly on its own if it truly cannot pay. That rule is
already written into `foundation` and this must not break it.

---

## E. Order, and why

1. **The pre-flight (D).** Half a day, touches three files, saves the owner twenty wasted minutes
   every time. Nothing depends on it.
2. **The search picture (B).** Pure assembly from files that already exist, plus one render
   function and one non-blocking artifact announcement.
3. **The live Library (C).** The real work, and the only piece with a migration risk. It also
   consumes B's pattern, so doing B first means C inherits a proven mechanism.
4. **Spokes onto the sheet (A1).** Small, and it closes a loop that has been open since the
   research layer was built.

---

## F. Answering "is it a tool, or a workflow"

He asked this directly and it is a fair question, because the answer is different for each.

- **D, the pre-flight: neither.** It is a guard inside an existing tool, in the same shape as
  `require_traffic`. Nothing new is registered and the model never sees it.
- **B, the search picture: not a tool either.** It is a step inside `run_research`, which is already
  a tool. It writes a file and announces it. Adding a tool would let the model decide whether to
  show it, which is exactly the wrong owner for that decision.
- **C, the live Library: not a tool.** It is the loop and the store. The model has no business
  knowing the Library exists mid-run.
- **A1, spokes: a source inside `merge.py`.** Not a tool.

**So: none of these are new tools.** That matters. Every tool added is another thing the model can
choose wrongly, and the registry is already at eleven. These four are all plumbing between steps
that already exist, which is the right place for work whose timing must not be a judgement call.
