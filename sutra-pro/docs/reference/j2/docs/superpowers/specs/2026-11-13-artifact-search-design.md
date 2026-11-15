# Artifact search: which finished artifact solves part of a new goal

Revision 2 (13 Nov, after a literature pass; the founder rejected the current `find_artifact` logic).
Base: `origin/main` at `e283bef0`. Companion to `2026-11-13-artifact-library-reuse-design.md` (the content door).
This spec is the plan-time door: before Adaptation commits to building, find the artifacts on Shelf 1 that already
are a proposed workflow's output, so the plan *uses* them instead of building them. Sources: Master Spec v1.1
p11-12, p25-26; Consolidated p6, p12, App. E; PRD 5 Nov p4, p9, p22; 13 Nov meeting; code: `find_artifact` :3132,
`run_artifacts` :2875, `run_slots`, `slotted`, `run_template_match` :2481, `folder_reuse` test,
`fixtures/folder-run/`; and the papers listed under "What the research says".

## The question, made precise

A new charter has N done-when items and a set of facts. Adaptation drafts a plan of workflows. The library has K
finished artifacts (K may be 1,000). For each proposed workflow: is there an artifact whose *verified effects*
cover this workflow's done-test, whose *inputs* this charter can supply, and whose *evidence* is good enough to
try before we re-verify? Matching is per workflow, not per goal: a plan of ten workflows may borrow two and build
eight.

## What is wrong with `find_artifact` today

`find_artifact` scores 0.5 x same business + 0.5 x share of the need's words found in the source run's charter.

| Problem | Why it fails | Example |
|---|---|---|
| It matches words of the old *prompt*, not what the artifact *does* | the charter says who it was for, not what it achieves | the copier's charter: "Northwind Archive, scans-inbox"; the need: "photos, Camera, Backup". Zero overlap. |
| Half the score is "same business" | penalises exactly the artifacts worth borrowing across clients | a copier built for an archive is most useful to everyone else |
| It never reads inputs or outputs | cannot tell whether the artifact can be run on this charter's facts | a form handler that needs a field this client does not have ranks the same as one that fits |
| One formula, no second opinion, no test | a near miss and a hit get the same treatment | CoSQA+: models "focus on semantic similarity rather than execution logic" |
| Nothing learns from use | the 1,000th search is as blind as the first | a card that was borrowed five times and worked still ranks by word overlap |

The candidate-with-reasons *shape* it returns is good and is kept. The score and the index are replaced.

## What the research says (and what we take from each)

| Finding | Source | What we take |
|---|---|---|
| General retrievers do badly at picking tools; enriched tool documents plus a reranker is the fix | ToolRet benchmark (Shi et al. 2025, arXiv 2503.01763); "Tools are under-documented" (Lu et al., ICLR 2026, arXiv 2510.22670): expand each tool with function description, when-to-use, limitations, tags, example usage | write a structured card per artifact at store time, with those five fields plus ours |
| Index each tool by *synthetic user questions* it would answer; at query time, extract the user's *intent* and drop the surrounding context | Re-Invoke (Google, EMNLP 2024 Findings, arXiv 2408.01875): 10 synthetic queries per tool, intent extraction per request; +20% single-tool, +39% multi-tool nDCG@5 | 10 "asks" per card; one intent-extraction call per plan that rewrites each workflow into capability language with the client's values slotted out |
| Key a skill by an LLM-written description of what it does; value is the code; only verified skills enter; retrieved skills are shown as examples | Voyager (Wang et al. 2023, arXiv 2305.16291) | the card's one-line "does"; audit-passed artifacts only; the top cards go into the judge's prompt |
| Induce reusable workflows from successful runs and replace instance values with variables | Agent Workflow Memory (Wang et al. 2024, arXiv 2409.07429) | slotting of done-when items and inputs (Kaivan's `run_slots`); the card learns from successful uses |
| Embed a hypothetical ideal answer rather than the raw query; hybrid (lexical + dense) retrieval; reranking only reorders what first-stage retrieval found, so recall first | HyDE; "Searching for Best Practices in RAG" (arXiv 2407.01219); RankGPT-style listwise reranking | the intent call also writes the ideal card line; BM25 and dense, fused; recall top 20 before any model judges |
| Retrieval beats a full catalogue in the prompt; hybrid lexical + semantic is the lever at thousands | RAG-MCP (arXiv 2505.03275); practitioner reports on MCP registries | never show a model the whole shelf; filter and recall first |
| Signature or type matching alone finds little; text plus tests and contracts finds the right code; test-driven agents reach the highest accuracy | Brown S6 (Reiss, semantics-based code search); CoSQA+ (arXiv 2406.11589) | inputs and outputs as a hard filter, never the match; the artifact's own test, then a sample run with mapped inputs, before anything is trusted |

## The unit of reuse is a workflow's output

A whole PRD is rarely reusable; one workflow's output often is. Shelf 1 records artifacts at this grain (each
section nested with the workflow that wrote it and the template it filled), so the unit has an address:
`<run>/<type>/<section>`, or the folder for a script. Cards and search work at this grain. The run itself is
reused as a run template (already exists). A whole document is reused only when every section's card fits.

## Three classes, from the dependency footprint

What makes an artifact portable is what it depended on. Every specialised section template records
`context.facts_used`, the charter facts the section was written from. That list, slotted, gives the class:

| Class | `facts_used` after slotting | Example | Travels to | Match key |
|---|---|---|---|---|
| Client-bound | several client facts | Users section, a studio's style guide | the same client (content door) or, since 13 Nov, another client if every check passes | facts fingerprint, then checks |
| Domain-standard | none, or subject words only | Chess rules, an accessibility checklist | anyone with the same subject | intent words vs the card's "does" and asks |
| Capability | only slots (inputs) | file copier, email sender, a connector | anyone who can supply the inputs | effect contract: inputs -> effect, business-free |

Business proximity is a tiebreak for client-bound cards only. For the other two it is ignored.

## The card, written once when an artifact enters the shelf

Everything the search reads is computed at store time. Query time reads cards, never run folders. Two LLM calls per
artifact at store time (profile, asks), one embedding call; or the mechanical fields alone when no model is on.

```
{
  "id": "j2-20261113-090000/script",
  "type": "script", "form": "folder", "class": "capability",          # mechanical
  "effects": ["copies every file from <folder A> to <folder B>, keeping sub-folders",
              "a file already there with the same bytes is left alone"],   # slotted done-when items that PASSED
  "inputs": ["<folder A>", "<folder B>"],  "outputs": ["copied paths, one per line"],
  "facts_used": [],                                                        # from the template context
  "invoke": {"entry": "copy_files.py", "usage": "python3 copy_files.py <from> <to>",
             "test": "test_copy_files.py", "needs": ["python3"]},
  "evidence": {"audit": "pass", "done_when": "5 of 5", "live": false, "used_by": 1,
               "verified_uses": 1, "failed_uses": 0, "date": "2026-11-13"},
  "profile": {                                                             # LLM, document-expansion fields
    "does": "Copies every file of one folder into another, keeping sub-folders; identical files are skipped.",
    "when_to_use": "any job that must move or back up all files of a folder and report what moved",
    "limitations": "local folders only; no filtering by file type; no deletion at the source",
    "tags": ["files", "folders", "copy", "backup", "move", "mirror", "report"],
    "example": "python3 copy_files.py C:/Camera D:/Backup  -> prints the paths it copied"
  },
  "asks": [                                                                # LLM, 10 synthetic user requests
    "move all my photos from one folder to another and tell me what moved",
    "back up a directory to another drive", "mirror a folder, skip files already there",
    "copy everything in a folder including subfolders", "...6 more"
  ],
  "embedding": [...],                                                      # of does + effects + tags + asks
  "learned_asks": []                                                       # real needs that found and used it
}
```

Only an artifact whose stage passed audit gets a card (Voyager's gate). The card lives as `card.json` beside the
artifact's data in the run folder and travels with the run on Git (decided 13 Nov). An index of all cards is
rebuilt from the runs folder on load and cached.

## The search, per proposed workflow

```
Adaptation drafts the plan as today  ->  for each proposed workflow W:

STAGE Q  INTENT                      one LLM call per plan, all workflows at once
         from W's name, goal, done-test, covered items and inputs, write:
           intents: 1-3 capability requests in user words, client values slotted
                    ("copy every file from <folder A> to <folder B> and list what was copied")
           ideal:   the one-line card.does the perfect artifact would have (HyDE)
           needs:   the inputs W can supply from the charter, the form it expects (if any)
         refused when an intent names a fact the charter does not hold

STAGE 0  HARD FILTERS                set tests over all K cards                  ms
         audit pass; not mock when this run is live; form compatible when W names one;
         every required card.input fillable from `needs` (else "not applicable: no <x>");
         authority (later). Shelf unreadable -> UNKNOWN, never "none".

STAGE 1  RECALL, HYBRID              top 20                                       ms
         lexical: BM25 over does + effects + tags + asks + learned_asks, query = intents + ideal
         dense:   cosine of embed(intents + ideal) vs card.embedding
         fuse:    reciprocal rank fusion of the two lists
         class tiebreak: client-bound cards get business proximity; others do not

STAGE 2  COVERAGE SCORE, WITH REASONS  top 20, deterministic                      ms
         covers      share of W's done-test clauses matched by a card effect (slotted Jaccard >= 0.5)  0.45
         footprint   capability: inputs fillable (already filtered) -> 1;
                     domain-standard: facts_used empty -> 1; client-bound: facts fingerprint equal
                     -> 1, else share of facts_used present, contradicted fact -> hard fail           0.20
         evidence    audit, done_when passed/of, live, log(verified_uses+1) - failed_uses, freshness  0.20
         fit         same form; what it read exists in this run; limitations do not name W's need      0.15
         -> candidates with score and reasons, the same shape find_artifact returns today

STAGE 3  JUDGE, LISTWISE             top 5, one LLM call per plan (all W batched)   ~5k tokens
         sees W (goal, done-test, inputs) and each card (profile, effects, inputs, invoke, evidence)
         answers per card: USE_AS_IS | USE_WITH_INPUTS {mapping} | ADAPT {what to change} | NO,
                           covers: [done-test clauses], confidence, reason
         refused when it names an input not on the card or a clause not in W (generator refusal pattern)

STAGE 4  VERIFY BY EXECUTION         the chosen card only                          sandbox, no model
         capability: copy the artifact folder into the run; run card.invoke.test; then run it with the
                     mapped inputs on a sample; check W's done-test -> receipts
                     ADAPT: the builder writes an adapter around the artifact (the founder's "USB cover")
                     with its own test, inside today's attempt budget; verify again
         document section: the content door (validate, render, receipts)
         pass -> the plan row becomes "use <artifact>" (or "adapt <artifact>") with receipts attached
         fail -> build as today; the reason and the failed receipt are recorded on the card as a failed use

LEARN    after the run: a verified use appends W's intent to card.learned_asks and bumps verified_uses;
         a failed use bumps failed_uses with the reason. The index is rebuilt on next load.
```

Composition: greedy set cover over the plan's workflows by Stage 2 score, one owner per done-when item (the
charter-change rule R1/R2). Remaining workflows build as today.

## Why this should find the copier where `find_artifact` cannot

```
need (Rubak):   W-2 "write a copier": goal "put every photo from C:\Camera into D:\Backup and list what moved"
STAGE Q:        intents ["copy every file from <folder A> to <folder B>", "list the files that were copied"]
                ideal   "Copies all files of one folder into another and reports what it copied."
                needs   {<folder A>: C:\Camera, <folder B>: D:\Backup}, form: script
STAGE 0:        1,000 -> 38 (documents out by form; mock out; cards needing an input Rubak lacks out)
STAGE 1:        lexical: "copy every file folder list copied" hits asks[0] "move all my photos from one folder
                to another and tell me what moved" and tags; dense: ideal vs does = 0.86. Fused rank 1.
                (find_artifact today: 0 shared words with "Northwind Archive scans-inbox", another business,
                score 0.0 to 0.1)
STAGE 2:        covers 1.0 (both clauses), footprint 1.0, evidence 0.7, fit 1.0 -> 0.90, reasons listed
STAGE 3:        USE_WITH_INPUTS {src: C:\Camera, dst: D:\Backup}, covers both clauses, confidence 0.9
STAGE 4:        test_copy_files.py ok; 3-file sample: 3 files land, 3 paths printed -> receipts
LEARN:          card.learned_asks += "put every photo from <folder A> into <folder B> and list what moved"
```

And the chess case: W-1 "Chess rules" -> intent "the complete rules of chess with every legal move type" ->
lexical hit on tags {chess, rules} and asks ("write the rules of chess for a game"), dense on does; footprint 1.0
(facts_used empty); judge USE_AS_IS; verify = W-1's own checks on the section -> receipts.

## Borrowing code: what "extract" means

The unit extracted is the artifact's whole folder (entry, test, README, data files), never a snippet, so its test
travels with it. The card's `invoke` block says how to call it. Three cases:

| Case | What happens | Who writes code |
|---|---|---|
| Inputs map one-to-one | the "use artifact" workflow runs `invoke.usage` with the mapping | nobody |
| Inputs close, shape differs (a list where it wants a folder, a different file name) | the builder writes an adapter script that calls the artifact, with a test; both tests must pass | the builder, inside today's budget |
| Behaviour differs (zip instead of copy) | ADAPT: the builder starts from the artifact's code as a draft | the builder |

The adapter is the founder's "cover so it fits the Sutra graph": the artifact stays untouched and reusable; the
adapter belongs to this run and gets its own card if it passes audit.

## Evaluation: how we will know it is better

ToolRet's lesson is that retrieval for tools must be measured on tool tasks, not assumed. Before the judge or
verify stages are wired to change a plan, build a small benchmark from what the library already holds:

| Set | Need | Correct answer | How many today |
|---|---|---|---|
| Leave-one-out | every workflow of every run template, as a need | its own artifact | ~60 pairs from 4 run templates |
| Cross-business | the pilates run's workflows | the yoga run's sections (adapt or reuse) | ~20 |
| Capability | "move my photos", "back up a folder", "mirror a directory" | the copier fixture | 3 hand-written |
| Negatives | needs with no answer on the shelf (a payment step, a chat bot) | none | 5 hand-written |

Report recall@5 and recall@20 after Stage 1, precision of the Stage 3 verdict, and end-to-end verified reuse
rate. The current `find_artifact` is the baseline. Weights in Stage 2 and the asks count are tuned on this set,
and the set grows by one pair every time a real run verifies a reuse (the LEARN step).

## Cost and scale

| Stage | Work at K = 1,000 | Cost |
|---|---|---|
| Card | once per artifact at store time | 2 LLM calls (profile, asks) + 1 embedding; mechanical fields free |
| Q | once per plan, all workflows batched | 1 LLM call |
| 0, 1 | BM25 inverted index over ~15,000 short strings; 1,000 vectors in memory | milliseconds |
| 2 | 20 cards x N workflows | milliseconds |
| 3 | once per plan, top 5 per workflow, batched | 1 LLM call |
| 4 | one sandbox run per chosen artifact | seconds, no model |

A build costs 1 to 3 model calls per workflow. The search costs 2 per plan and pays for itself when it removes
one workflow.

## What the founder's rules forbid

- No match on names or business words for capabilities (Spec p12).
- A found artifact is not a satisfied condition until Stage 4 passes (PRD p2; Consolidated p6).
- A shelf that cannot be read is UNKNOWN (Spec p12; PRD p9).
- Partial fit routes to ADAPT before BUILD (Consolidated p6).
- The judge reads cards and the need only; it never reads an artifact's content (no invented facts).
- An intent that names a fact the charter does not hold is refused (no invented inputs).

## What exists to build on

| Piece | Exists | Reuse |
|---|---|---|
| Per-artifact record with checks, files, template, sections | `run_artifacts` :2875 | evidence, outputs, invoke.entry |
| Slotting charter values out of text | `run_slots`, `slotted`, `with_slots` | effects, intents |
| Candidate shape with reasons | `find_artifact` :3132 | keep the shape, replace the score and the index |
| Word tokeniser and stop words from data | `words`, `templates/library-settings.json` | BM25 tokens |
| Judge with refusal and structured reply | realization judge, template generator refusal | Stages Q and 3 |
| Sandbox test run | `folder_reuse` runs `test_copy_files.py` with `subprocess` | Stage 4 |
| Single owner per item | `plan_faults` R1/R2 | composition |

## Decided

Runs are pushed to Git (13 Nov). Cards live as `card.json` beside the artifact in the run folder and travel with
it. Hybrid retrieval (lexical plus dense) from the start: the dense half is the one that finds "photos" when the
card says "files", and at today's size one embedding call per artifact is cheap. Cross-client reuse is a yes for
now (13 Nov), so client-bound cards are candidates too, with the checks as the guard.

## Not decided here

Which embedding model (any small one works at this size; the choice can change without touching the cards).
Authority and policy filters. The "use an artifact" workflow kind and the sandbox it runs in, which this search
needs but does not define.

## Tasks, Impact and Effort

| # | Task | Impact | Effort |
|---|---|---|---|
| 1 | Card builder: mechanical fields from run records; profile and asks by one LLM call each; `card.json` at Done | the index exists, in the words people search with | 4 h |
| 2 | Index and Stage 0-1: BM25 over card text, embeddings, reciprocal rank fusion, hard filters | 1,000 artifacts in ms, recall first | 3.5 h |
| 3 | Stage Q intent extraction: prompt, schema, refusal, mock | the query in capability language | 2 h |
| 4 | Stage 2 score with reasons, replacing `find_artifact`'s score; `find` keeps its shape | explainable ranking | 2.5 h |
| 5 | Benchmark from run templates plus hand pairs; recall@k and verdict precision; baseline = today's `find_artifact` | proof it is better, before it changes a plan | 3 h |
| 6 | Stage 3 listwise judge: prompt, schema, refusal, mock | the decision with inputs mapping | 3 h |
| 7 | Stage 4 verify: sandbox test, sample run, receipts; adapter path for capabilities; content door for sections | nothing trusted unverified | 6 h |
| 8 | LEARN: learned_asks, verified and failed uses on the card; index rebuild | the library gets better with use | 1.5 h |
| 9 | Adaptation wiring: call per proposed workflow, "use artifact" rows, set cover (Rubak) | the plan borrows instead of builds | 4 h |

About 29.5 h. Tasks 1 to 5 stand alone and give a measured answer to "is it better" before anything changes a
plan. Task 9 needs the "use an artifact" workflow kind.
