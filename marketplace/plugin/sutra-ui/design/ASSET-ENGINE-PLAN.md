# Layer 02 in Sutra — the asset engine, the ideas tab, and how the agent asks

**status**: proposed, not built · **written**: 2026-09-09 · **supersedes**: nothing

## What this is

Porting layer 02 (`workflows/02-asset-engine/`) into Sutra, plus the user journey the owner
described: the agent asks for its gates in the chat, the result lives in a new tab, and an article
run starts from an idea rather than from a topic somebody typed.

The load-bearing insight: **the machinery already exists.** `seo_agent/tools/onboard.py` (shipped
2.249.0) asks a person a question in the chat, waits, records the answer, and carries on. Every
gate below is that same mechanism used again. Nothing new has to be invented for "the agent asks".

---

## 1. The engine: one tool, five builders, three gates

A new work tool `build_assets`, declared in `registry.py`, shaped exactly like `learn_brand`:
resumable, one named file per builder, one builder failing does not lose the other four.

```
seo_agent/assets/
  _common.py        read/save under knowledge/assets/, the shared Ownability + Linkability tests
  scope.py          builder 0 — brand scope, the one anchor all three methods judge against
  competitors.py    builder 1 — method 1: who earns links, and the FORMAT that earned them
  formats.py        builder 2 — method 2: the swipe library, transplanted
  trends.py         builder 3 — method 3: subreddits -> tensions -> ideas
  merge.py          builder 4 — stack, embed, block, adjudicate SAME/COMBINE/SEPARATE
  reuse.py          builder 5 — do we already have it (wraps the EXISTING reuse check)
seo_agent/tools/build_assets.py     the driver
seo_agent/prompts/assets/*.md       one file per model call
```

Writes `knowledge/assets/{scope.md, competitors.json, formats.json, trends.json, ideas.json}` plus
`_work/` per builder, mirroring `knowledge/brand/`.

### The shared tests (F5: one concept, one wording)

`assets/_common.py` owns **Ownability** and **Linkability** as single named functions with a single
prompt each. All three methods call them. The original's whole comparability argument rests on this;
three paraphrases cannot be merged or ranked against each other.

### The three gates, and where they wait

Each is `loop._wait(kind="question")` with an `asset_gate` field, resumed the way `onboard`'s
`interview` field is. No second waiting mechanism.

| # | Gate | Asked | Why it is a gate in the original |
|---|---|---|---|
| G0 | "This needs your time: about N questions, and the competitor list needs your eye. Start now or later?" | before builder 0 | the owner's requirement: say the cost upfront |
| G1 | the 15-competitor shortlist, split direct / adjacent | after builder 1 step A3 | `competitor-study.workflow.md:154` "Get the user's sign-off (this is a gate)" |
| G2 | the subreddit list | after builder 3 phase A1 | `study-trends.workflow.md:54` "Get approval (this is a gate)" |

G1's approved list is written to `knowledge/competitors.json` — **the same file the Knowledge tab
textarea writes today**, so removing that textarea loses nothing and the two can never disagree.

### What is blocked, and the engine must say so

Method 1 step B is a paid DataForSEO pull (each competitor's link-earning pages). Balance is
-$0.07. So G0 must state honestly which methods can run today:

- method 1 — needs DataForSEO. Refuses with a plain message, like `learn_brand` does for traffic.
- method 2 — free, model only.
- method 3 — free, but Reddit refused every check on 2026-09-09; `field_sources.py` already records
  that as "unknown", never "empty". The engine inherits that honesty.

An engine that runs 2 of 3 methods must SAY it ran 2 of 3, on the tab and in the summary.

---

## 2. `ideas.json` — the schema

One row per idea, from the original's merged schema (`4-merge/README.md:25`) plus what Sutra needs
to track state:

```json
{ "id": "a0042",
  "title": "...", "angle": "...", "format": "benchmark report",
  "method": ["competitor-study", "study-trends"],      // all methods that found it, after dedup
  "brand_fit": "CORE|TRANSPLANT|ADJACENT", "transplant_from": "",
  "ownability": {"verdict": true, "why": "..."},
  "linkability": {"score": 4, "of": 4, "why": "..."},
  "beatability": 2, "effort": "M",
  "proof": [{"url": "...", "domains": 136, "what": "..."}],
  "reuse": {"verdict": "brand new|improve existing|build from parts|already have it",
            "links": [], "why": "..."},
  "rank": 12,
  "status": "open|building|done|dropped",
  "built": {"library_id": "", "run_id": "", "at": "", "how": "from_idea|matched"} }
```

`status` and `built` are Sutra's, not the original's. Everything else traces to a named step, so the
tab can show provenance per field.

---

## 3. Ticking an idea off

**Provenance only. One mechanism, no judgment.**

When a run starts from an idea, the idea's id rides on the run: into `state.json`, then onto the
library item's meta at `loop.save_to_library()`, which sets `status: done` and `built.library_id`.

That is the ONLY thing that ever ticks an idea. An article the owner typed himself never ticks
anything, and nothing is ever matched by meaning.

Decided 2026-09-09 by the owner, and it is the right call. The alternative was matching hand-written
articles against open ideas by embedding and proposing "this looks like you already wrote this".
That adds a whole class of wrong answers to save a rare piece of bookkeeping. Every finished article
lands in the Library regardless, so nothing is lost by not tracking it twice.

## 4. "Write the next one" — a filled-in prompt, not a model decision

The owner's requirement: it should be a chip he clicks, which writes the message for him, and then
he presses send.

**The point of this design is that the model never picks the idea.** `GET /assets/next` returns the
highest-ranked idea with `status: open`. The chip renders above the composer carrying that idea's
**id in a data attribute**. Clicking it fills the composer with a message that NAMES the id:

> Write the next asset idea: **a0042 — Cost of a Bad Hire, benchmarked**

So by the time the model sees anything, the choice is already in the text. There is no "the agent
should remember to look at the sheet" step that can quietly not happen. The id is data on a button,
not an instruction in a prompt.

Typed by hand instead of clicked, it still works: `loop._knowledge_block` carries one line naming
the top open idea, the same way it now carries whether the setup interview has been put. The model
reads it as context, not as a rule it might forget.

The chip's own text also carries the warning the owner asked for, so it is on screen before he
sends, not after:

> This can still be turned down at the topic gate, which reads the live search results. If they
> argue for a different intent, I stop rather than write the wrong article.

## 5. What gets deleted

**`tools/suggest_topics.py` goes.** Its method (pick one competitor, read what they rank for,
propose six topics) answers "what do they rank for", not "what earns links". Once the engine exists
there are exactly two ways to start an article: pick from the sheet, or type your own.

**The Competitors textarea in the Knowledge tab goes.** Competitors are set at G1, in the chat,
where the agent proposes a measured shortlist and the owner approves it. Typing names into a box
with no evidence behind them is the thing the gate replaces.

**SEQUENCING, and this is not negotiable:** both deletions ship in the SAME release as a working
engine, never before. Deleting `suggest_topics` first leaves a user with no way to get an idea at
all. Until then the engine is additive.

---

## 6. The tab

Fifth item in the settings rail, after Knowledge / Memory / Library / Tools: **Asset ideas**.

`GET /assets` → `{built_at, methods_run, methods_blocked, counts:{open,done,dropped}, rows:[...]}`
`GET /assets/{id}` → one idea with its full proof and reuse detail
`POST /assets/build` → starts the engine (or resumes it at its next gate)
`POST /assets/{id}/status` → the owner drops, reopens, or confirms a proposed match

Screen: a count line in the catalogue's voice ("142 ideas · 31 done · 2 of 3 methods ran, the
competitor study needs DataForSEO"), a filter by method and by reuse verdict, and a table ranked
best first. Clicking one opens it in the right-hand panel with its proof, the way a brand file does.

Empty state: what the engine does, what it will ask for, and the one button.

---

## 7. Prompting the owner when it has not been built

- **In the setup interview**, as a final optional question: "Shall I also work out what to write
  about? It takes longer and I will need you twice." Skippable, recorded as skipped.
- **On New chat**, when `ideas.json` is absent and setup is done, one quiet line above the composer.
  Not a modal, not a nag, dismissible, and it never appears once the engine has run.

---

## 8. The writer brief box (separate, small)

`.ag-brief` max-height drops from 62vh to about 30vh, and an **Open** control beside the heading
opens `writer-brief.md` in the right-hand panel at full length. The panel route already exists
(`brandfile` action). One CSS change, one button.

---

## 9. Build order

1. The brief box + Open (30 minutes, unrelated to the rest, ships immediately)
2. `assets/_common.py` + `scope.py` + the two shared tests
3. `trends.py` (method 3) — free, and the subreddit finder already runs
4. `formats.py` (method 2) — free
5. `merge.py` + `reuse.py` (wraps the existing reuse check)
6. The tab + endpoints
7. The gates, ticking, and "write the next one"
8. `competitors.py` (method 1) — last, because it is blocked on DataForSEO
9. Delete `suggest_topics` and the competitors textarea, same release as 7

Methods 2 and 3 alone give a working sheet. Method 1 makes it good.

---

## 10. Risks

- **Cost.** Method 1's step B is a paid pull per competitor. Guard it the way `serp_advanced` is
  guarded: a balance floor checked before the first call, refuse cleanly, spend nothing.
- **Rubbish at volume.** The original names three traps step G is designed against precisely because
  this step produces plausible nonsense at scale. Port the traps, not just the step.
- **The self-audit gate** in method 3 (`study-trends.workflow.md:231`) exists so a tension cannot be
  quietly dropped. Port it.
- **Judging blind.** Ownability and Linkability must be handed the brand scope and the competitor
  set, or they guess generously. This is the exact failure that fired a flag on 14 of 18 sections
  once before.
