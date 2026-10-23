# J2.b with no template: the M6.1 desk spike

| Field | Value |
|---|---|
| **status** | v2, 2026-10-23; step M6.1 of [PRD-FIVE-FUNCTIONS.md](PRD-FIVE-FUNCTIONS.md). MK-3 in the [decision log](PRD-FIVE-FUNCTIONS-DECISIONS.md) takes it as marked, and M6.3 to M6.5 build from it |
| Evidence | A desk spike of the J2 prototype and Sutra's line code (decision C2: no live model runs), set out in Appendix A |
| The three runs | `j2-20261013-165916` (a PRD), `j2-20261014-111512` (a game) and `j2-20261016-160511` (documents, then a site), in `J2_Prototype/runs`. Their plans and costs are in Appendix C |
| Flag | `J2_ADAPT_MAKE` gates M6.3 and M6.4. With it off, nothing changes. It is on in Beta first (Q2) |

## The answer in short

1. **When.** Make runs when no Library line fits: an organic or default department, or a line Root's check refused.
2. **Reads.** The identity, the rules, the Library's engine and artifact use cases, and the kind's required engines. It reads neither the done line nor other departments' workflows.
3. **Levels.** Version 1 has level 1 (take) and level 2 (shape). Level 3 (probe) comes later.
4. **Shape.** Each engine is `{name, does, reads, writes, covers, confidence}`. A plan is the fewest engines that cover every item, usually two to five, with the required engines kept.
5. **Ask.** Below 0.6, or when a required engine cannot serve the goal, Identity asks one question and nothing is registered. From 0.6 to 0.8, the doubt is shown and nobody is asked.

## The proposal

| Row | What the build does | Builds in |
|---|---|---|
| J2B-1 · When Make runs | When the kind has no line (organic), when it is default (Do is a fallback, not a fit), or when Root's check refused the line. A reshape keeps the kind's required engines (website: Check, Q12) at level 1. If one cannot serve an item, Make answers `cannot` and returns no plan. Check, for example, cannot pass a game's script. | M6.3, M6.4 |
| J2B-2 · Practices read | Names and use cases, never files: `rules`, `engines` (the shipped work engines, except Setup), `artifacts`, `required` (each with what its check refuses) and `taken`. Not the kind's done line, which the items replace, and not other departments' workflows until Learn. | M6.3 |
| J2B-3 · Levels | Level 1 takes a shipped engine with its template's reads, writes and start. It does so when the use case fits and the engine reads the Brief or an artifact in its own form. Level 2 shapes a new engine, born after Priority and Root (Q5). A shaped writer that a level-1 engine reads is born with the reader's form, and code holds it there. | M6.4 |
| J2B-4 · Shape | Each engine also has `doubt` (filled below 0.8) and `internet`. `c_line_is_engines` refuses a missing field, a confidence outside 0 to 1, an unknown item, a level-1 engine off its template, and a dropped required engine. `cannot` passes only for a required engine. | M6.4 |
| J2B-5 · Size | The fewest engines that cover every item, required ones included. A plan is one engine only when it is Do and the items make one answer. Code sets no cap (Q11). | M6.4 |
| J2B-6 · Covers | An engine covers an item when Audit reads the item in its output, or when the item restates a rule the engine holds. Code checks that every item is covered, that every engine covers an item or feeds a later one, and that every required engine is in the plan. | M6.4 |
| J2B-7 · Ask (FA1.3) | Code reads the lowest confidence. At 0.8 or more, the plan goes to Priority. From 0.6 to under 0.8, it goes with the doubt shown. Under 0.6, Identity asks one question and nothing is registered. `cannot` is a conflict, and Identity asks it as one question with code-built options (M3.5). | M6.4, M6.5 |
| J2B-8 · The question | 'Before I set up the work for {department}: {the doubt} Unless you say, {the fallback}. Answer in your own words, or say "just do it".' It shows no number and names no internal part. | M6.4 |
| J2B-9 · Offline | Today's draft stays (`d_adapt_line`; a default department keeps Do). It carries no confidence and asks no question. | M6.4 |

## Three worked examples

### A · LabSlot, a PRD (default, or organic)

Items: D1 problem; D2 users; D3 goals; D4 book, cancel, availability; D5 phones; D6 80% without staff; D7 out of scope holds no must-have; D8 LabSlot throughout.

| Engine | Level | Does | Reads > writes | Covers | Confidence |
|---|---|---|---|---|---|
| Requirements | L2 | Lists R1 to R4, each traced, then out of scope | Brief > Requirements | D4, D5, D7 | 0.9 |
| PRD | L2 | Writes every section, naming LabSlot | Requirements > PRD | D1, D2, D3, D6, D8 | 0.85 |

The lowest confidence is 0.85, so the plan goes to Priority with no question.

### B · Tap Rush, a browser game (organic only)

Items: D1 name; D2 start screen; D3 score and timer; D4 30-second round; D5 1 point a circle; D6 a circle lasts 1 s; D7 end screen; D8 tap or click; D9 look; D10 no overflow; D11 one file, no forms; D12 no script errors.

| Engine | Level | Does | Reads > writes | Covers | Confidence |
|---|---|---|---|---|---|
| Play rules | L2 | Writes the rules with the brief's numbers | Brief > Play rules | D4, D5, D6, D8 | 0.9 |
| Game | L2 | Builds the three screens as one page | Play rules > Live site | D1, D2, D3, D7, D9, D10, D11, D12 | 0.7, doubt: how often circles appear |

The lowest confidence is 0.7, so the plan goes to Priority with the doubt shown. Check and Publish are left out and named (Q13). In a website department, Check is required and fails the game's script, so Make answers `cannot`.

### C · Brew Lab, documents, then the site (a refused website line, or organic)

Items: D1 PRD; D2 design; D3 name and address; D4 menu with prices; D5 hours; D6 phone and email; D7 pre-order form to the shop; D8 no payment field; D9 phones; D10 live.

| Engine | Level | Does | Reads > writes | Covers | Confidence |
|---|---|---|---|---|---|
| PRD | L2 | Writes R1 to R7 | Brief > PRD | D1 | 0.85 |
| Design | L2 | Writes each section and field, with its requirement | PRD > Design | D2 | 0.85 |
| Site | L2 | Writes the page in the Pages form Check reads | Design > Pages | D3, D4, D5, D6, D7, D9 | 0.45, doubt: where a pre-order goes |
| Check | L1, required for website | Holds the page to your rules and builds it | Pages > Build | D8 | 0.9 |
| Publish | L1 | Puts it live after your first yes | Build > Live site | D10 | 0.9 |

The lowest confidence is 0.45, so Identity asks where a pre-order goes. With the answer, Site is reshaped at 0.85.

## Marked

MK-3 takes this file as marked. The owner said on 2026-10-23: 'the adaptation here is the logic where you don't need my input'. So the build takes **every row as keep**, with no owner input. A change to a row reopens only the steps it opens. M6.2 writes the marks onto the site's J2.b and FA1 rows. Still pending under C2: the three briefs, run live on Beta.

| Row | Mark | Opens |
|---|---|---|
| J2B-1 When Make runs | keep | M6.3, M6.4 |
| J2B-2 Practices read | keep | M6.3 |
| J2B-3 Levels | keep | M6.4 |
| J2B-4 Engine shape | keep | M6.4 |
| J2B-5 Size | keep | M6.4 |
| J2B-6 Covers | keep | M6.4 |
| J2B-7 Confidence rule | keep | M6.4, M6.5 |
| J2B-8 The question | keep | M6.4 |
| J2B-9 Offline | keep | M6.4 |

## Appendix A · Detail and evidence, row by row

**Sources.** The prototype was read at `agents/j2/adaptation.md` and in `j2.py`: `_turn_adaptation`, `_atoms_checked`, `_plan_checked`, `_lld_gaps` and `_usable`. Sutra was read at `adapt_source`, `p_adapt_line`, `d_adapt_line`, `_root_check`, `_line_faults`, `do_file` and `engine_check`, and at the four kinds in `engine_defs/website.json`.

**J2B-1.** The reshape path is the one `adapt_source` already has. Root's check refused the line, whatever its source. For example, a website department's words may ask for work the website line cannot cover. M5.1 names the uncovered items, Root's check refuses the line (M7.2: every item covered), and the reshape goes to Make.

`c_line_is_engines` refuses a plan that drops a required engine, as Root's check does from M4.4 ('no required engine is left out', M7.2). Otherwise a reshape would drop Check, be refused again, and end blocked after `J.REPAIRS`.

On a `cannot` answer, the covering posts one conflict to Identity, naming the engine and the items. No rule settles it, so the conflict goes to the owner. A plan that Root would refuse is never returned.

In a default department, Make may still return Do alone, at level 1.

**J2B-2.** The practices in place, decided candidate by candidate:

| Candidate | Read? | Evidence |
|---|---|---|
| The department's rules | **Yes**, each with its tag (`p_adapt_line` already passes them) | Tap Rush: the owner's rule 'no features beyond the three screens' lost to a website condition ('a nav reaches every section'). The second plan then added the nav the owner had ruled out. |
| The Library's engine use cases | **Yes**, with the artifact use cases. `engines` gives each engine's name, use case, reads and writes. `artifacts` covers Brief, Site plan, Pages, Build, Live site and Result. `taken` holds names only | Level 1 needs them. Today a shaped line may not use a Library name, so a second organic department births 'Facts 2' and 'Site 2' (`d_adapt_line`). |
| The kind's required engines | **Yes**. `required` gives each required engine with what its check refuses. For Check, that is a page with a script, a link to no page, and a page with almost no text (`engine_check`) | Rule 5 (S-06, S-21) and Q12. Without the names, a reshape drops Check. Without what Check refuses, Make shapes a game that Check fails. |
| The organisation's earlier registered workflows | **No**, until Learn (FA5) | The six Spark 2026 runs gave first plans of seven or eight workflows of the same shape with no memory, and both PRD briefs gave one workflow per section. Copying risks a line built for another goal. The prototype's memory was polluted with 109 mock playbooks. |
| The kind's done line | **No**. It survives only as D1 when Root drafted no items (M3.2 offline) | Tap Rush: website checks read the score's starting 0 as an invented number, which cost a second round. Organic's done line says nothing the items do not. |

**J2B-3.** The site names three levels and two logics, and leaves them empty (gap matrix AD-2). Level 1 is Cynefin's clear domain: a known practice fits. Level 2 is the complicated domain: the parts are known and the arrangement is not. Level 2 shapes from Do, as the organic path does today, and the engine is born into the records-home Library tagged `made_by`.

Level 3 is the complex domain: a probe whose result decides the next round. A probe pays only when a next round reads its result. That is Pursue (M9), and its lessons are Learn, a non-goal. In version 1, a level-3 situation shows up as low confidence, which becomes one question.

The chaotic domain (act first) belongs to Identity, acting on the rules.

Code decides the level. An engine named after a shipped template is level 1, and any other engine is level 2. Born engines are never taken, because their instruction carries another department's words.

*The artifact form.* A level-1 engine reads a Library artifact in the form the Library's own writer files it. Today the artifact's own check does not hold that form, and Pages is the case that matters.

The Library's Check (`engine_check`, `check_rules_of`) reads `_plan.json`. That is a JSON object whose `pages` list each `{slug, title}`, with `index` among the slugs, and optionally `site_name`, `tagline` and `palette`. It then reads each planned `<slug>.html` as the JSON object `{title, body_html}`, where `body_html` is the inside of `<main>`.

Only the Library's Write files Pages that way. The Pages check (`pages_have_html`) asks only that each `*.html` is non-empty. A born Pages writer files whole HTML documents and no `_plan.json` (`p_do_page`). Check then files a failed Build ('no home page'), or fails on a page it cannot read, and Publish never runs.

So M6.4 adds three things:
- `artifacts.py` gains `pages_are_checkable`. It checks that `_plan.json` parses and lists its pages, and that each planned page is JSON with a `title` and a `body_html`. The Pages template names it as its `form`. Scripts, text and links stay Check's verdicts.
- `_j2_settle` births a writer that a level-1 engine reads with that form. Its page step writes `body_html` with no script, linking only to planned slugs. `do_file` files `_plan.json` from its planned pages, and each page as `{title, body_html}`.
- `do_file` applies the form's check to that writer. Pages in any other form fail where they are written, never at Check.

A shaped Pages writer that no Library engine reads keeps today's form. With the flag off, nothing changes.

**J2B-4.** An example of one engine:

```json
{"name": "Site", "does": "writes the one page from the design, with the facts exactly as given",
 "reads": "Design", "writes": "Pages", "covers": ["D3", "D4", "D5", "D6", "D7", "D9"],
 "confidence": 0.45, "doubt": "When someone pre-orders, where should the order go? ...", "internet": false}
```

A `cannot` answer is `{"cannot": {"engine", "items", "why"}}`. It is accepted only for a required engine of the kind, with known item ids.

A refused engine goes back as a shape fault, twice at most, and then Identity tells the owner. It is never quietly dropped, as the prototype's `_atoms_checked` dropped engines, because dropping one would leave items uncovered.

**J2B-5.** Split a plan only where a rule or an item needs an artifact of its own, which a later engine or Audit reads by name. A plan of more than five engines says why in its message. Priority's room bounds the plan, and Root's check refuses more than six until M7.2 lifts that cap.

**J2B-6.** This follows the prototype's `_plan_checked` and `_lld_gaps`. A gap goes back once as a shape fault. M5.1's ledger warning and M7's refusal remain the backstop.

**J2B-7.** Confidence is the AI's estimate that this engine, reading what the plan hands it, can make its items true without a fact or decision nobody has given. Code in `adapt_line_offer` decides what happens next, never the AI.

Adaptation's pane (S8) shows the plan by its lowest confidence:
- 0.6 to under 0.8: 'Fairly sure', with the doubt under the engine.
- Under 0.6: 'Not sure', with 'Asked you'. This is an M0.5 ask, `missing: plan`. If the identity already answers the doubt (FI1.2), Identity hands that answer back without asking.
- A `cannot` answer: 'Cannot with this kind', with 'Asked you'.

The `cannot` options are built by code. One is to set the department up again, done its own way: a Root request with the same words, for the owner's stamp, because Root makes departments. Another is to leave the items out, which is a done_items ask. The third is to stop.

Bounds:
- One question per line request, and two per cycle (the `J.REPAIRS` bound).
- Posting the doubt ends the bargain thread, and the answer opens a new line request. No bound (4 hops, 15 minutes, spend) runs while the owner thinks.
- If a plan is still under 0.6 after the second answer, it goes to Priority, and the plan tell names the remaining doubt.
- A missing confidence is a shape fault, never a question.

J2.a asks *what*: goal, items and facts. A fact not given is marked to confirm (MK-1). FA1.3 asks *how*: a decision that changes which engines run or what one does.

No prototype run recorded a confidence, so 0.6 and 0.8 are a starting rule. Under it, the fully specified Tap Rush asks nothing. Brew Lab's order route, a decision that changes where an engine sends something, asks once. Everything in between is shown and not asked, because only a rule asks (S-18).

The rule keeps SM-8 within reach. Revisit the numbers if more than one in three no-template departments on Beta get a doubt question. Revisit them also if an item Audit reads as not met traces back to a decision that a plan scoring 0.6 or more never asked about.

**J2B-8.** For Brew Lab: 'Before I set up the work for Brew Lab Website: when someone pre-orders, where should the order go, for example an email to the shop? Unless you say, the form shows the order on screen for the customer to bring to the counter, and sends nothing. Answer in your own words, or say "just do it".'

For Tap Rush in a website department: 'Before I set up the work for Tap Rush: a website department checks that no page runs a script, and the game needs one. Shall Root set Tap Rush up as a department done its own way, or shall I leave the game out? Unless you say, nothing is set up.'

The fallback never reaches outside. 'Just do it' (`JUST_DO_IT`) takes the fallback, and the plan tell names it.

**J2B-9.** The offline plan says it was shaped offline. Its covers map every item to the last engine (M5.1).

**The examples in the runs.** Each brief's items are drafted as Root drafts them at J1 (M3.2), at the target level.

A (LabSlot):
- The rules were: every requirement traces to the problem or a must-have, and Out of scope lists only things that are not must-haves.
- The plan has two engines because both rules concern the requirements list, which Audit then checks by id.
- The run planned six section workflows. Its sibling run stalled after 25 calls with only 1 of 6 sections written.

B (Tap Rush):
- Check's layout would add a nav, which the rules refuse.
- In a website department, the game reaches Make only as a refused Library line. There, Make answers `cannot` with Check and D2, D3 and D12.
- The Play rules artifact holds the starting 0, which is what a 'no invented numbers' check reads.
- The run planned four workflows and was forced to add a nav. It met all 12 items, then made two fixes for the 0.

C (Brew Lab):
- J2.a asks for the menu, the hours and the address before Adaptation is asked. In the run, they were asked at message 177 of 236.
- The answer ('email it to hello@brewlab.example') reshapes Site. The first send still passes Identity's gate (J2.6).
- The run planned 31 workflows over nine cycles and spent the whole budget. It ended 'done with open items', an end Sutra does not allow (Q6).

## Appendix B · What M6.3 to M6.5 build

| Step | Builds | Its test |
|---|---|---|
| M6.3 | `adapt_source` adds `practices: {rules, engines, artifacts, required, taken}` (J2B-2) to the line request when the flag is on and the source is shaped | The request carries exactly those five keys: no done line, no other department's workflows and no file text. A website department's `required` names Check |
| M6.4 | `function-prompts/adaptation/make.md` and the no-template branch of `p_adapt_line` ask for the J2B-4 shape, or for `cannot`. `c_line_is_engines` checks J2B-4 and J2B-6, including required engines (M4.4's `required: true`). `_line_faults` lets a shipped engine stand at level 1. `adapt_line_offer` applies J2B-7 and turns `cannot` into a conflict with code-built options. The artifact form (Appendix A, J2B-3): `pages_are_checkable`, `form` on the Pages template, a born writer filing that form, and `do_file` applying it. `J.answer` records the plan ask | Organic and default plans cover their items. A website reshape keeps Check, and a stub that drops it is a shape fault. A stub `cannot` on a website game gives one question with the options. A stub at 0.45 gives one question and no registration. A stub at 0.7 shows the doubt and asks nothing. Offline keeps the draft. A shaped writer's Pages in the form pass Check and reach Publish, and whole HTML pages fail at the writer |
| M6.5 | Scenarios on organic and default: shape, bargain, Root's check, run, read | Both reach step 7 with a covering plan |

## Appendix C · The three runs, their plans and costs

All runs used Sonnet through `claude -p`. Calls and minutes come from `report.json`, and tokens from `calls.jsonl`. No price was recorded, so there is no USD figure. Credits are the prototype's rate-card units.

| Run | Brief | Plan (workflow: covers) | Cost | End |
|---|---|---|---|---|
| j2-20261013-165916 | LabSlot PRD | Problem: 1; Users: 2; Goals: 3; Requirements: 4, 5; Success metrics: 6; Out of scope: 7, 8. One fix after Audit (a double-booking metric) | 1 cycle; 33 calls; 9.1 min; 98 of 200 credits; 592k tokens in, 42k out. Adaptation 3 calls (9% of input), Coordination 7 (21%). 1 counter; 3 questions | Workable at v7 |
| j2-20261014-111512 | Tap Rush game | First plan: Shell: 9 to 12; Start: 1, 2; Play and loop: 3 to 6, 8; End: 7. A plan check (website N8) forced Minimal nav: 12. Two fixes for the score's 0 (website N6) | 2 cycles; 27 calls; 8.5 min; 136 of 200 credits; 536k in, 63k out. Adaptation 4 (13%), builders 9 (42%), Coordination 7 (27%). 0 counters; 0 questions | 12 of 12 items met. The run stopped at the account's spend limit |
| j2-20261016-160511 | Brew Lab, documents first | PRD: six sections plus 2 revisions; design (HLD): six sections plus 3; detailed design (LLD): five sections plus 3; site: Menu: 2; Pre-order: 5, 6; Address: 1, 4; Hours: 3; Layout: 7, 8; plus 1 revision. 31 workflows in all | 9 cycles; 115 calls; 30.1 min; 500 of 500 credits; 3.22M in, 194k out. Adaptation 12 (11%), Coordination 31 (26%), builders 35 (30%). 0 counters; 3 questions | Done with open items: the PRD was shipped with its no-invented-facts check failing |
| j2-20261013-185235 (contrast) | LabSlot PRD again | Six one-section workflows; Problem done, five held | 4 cycles; 25 calls; 10.6 min; 20 of 200 credits; 430k in, 37k out. Adaptation 6 calls (26%) | One section shipped |
| Six Spark 2026 runs (contrast) | One college tech fest brief, run six times | First plans of 7 or 8 workflows of the same shape: one per visitor need, plus a shell | 29 to 37 calls each; 78 to 131 credits | Five done; one done with open items |

In all three main runs, making the plan was the cheap part: Adaptation took 9 to 13 percent of input tokens, against 21 to 27 percent for Coordination. So one make step per request, at most two reshapes and one question round is the right budget for Make. On a first pass, the proposed plans need 2 (A), 2 (B) and 4 (C) model calls for the work, against 7, 9 and 35 builder calls in the runs.

provenance: {author: claude, date: 2026-10-23, inputs: [J2_Prototype 564e3a7 (agents/j2/adaptation.md, j2.py, runs/), sutra engine_runtime.py, website_dept.py, artifacts.py, engine_defs/website.json, engine-templates/, artifact-templates/], runs: desk read only, review: none by the owner yet, confidence: high on the evidence; the 0.6 and 0.8 thresholds are a starting rule with a stated reversal trigger}
