# J2.b with no template: the M6.1 desk spike

| Field | Value |
|---|---|
| **status** | v1, 2026-10-23; step M6.1 of [PRD-FIVE-FUNCTIONS.md](PRD-FIVE-FUNCTIONS.md). MK-3 in the [decision log](PRD-FIVE-FUNCTIONS-DECISIONS.md) takes this file as marked; M6.3 to M6.5 build from it |
| How it was made | A desk spike (decision C2: no live model runs). Read: the J2 prototype's Adaptation (`agents/j2/adaptation.md`; `j2.py` `_turn_adaptation`, `_atoms_checked`, `_plan_checked`, `_lld_gaps`, `_usable`) and its recorded runs; Sutra's `adapt_source`, `p_adapt_line`, `d_adapt_line`, `_root_check`, `_line_faults`, `do_file`, the Library's engine and artifact templates, and the four kinds in `engine_defs/website.json` |
| The three runs | `J2_Prototype/runs/j2-20261013-165916` (a PRD), `j2-20261014-111512` (a browser game), `j2-20261016-160511` (design documents, then a site). For contrast: `j2-20261013-185235` (the same PRD brief, failed) and the six Spark 2026 runs (one brief, run six times). Plans and costs are attached at the end |
| Flag | `J2_ADAPT_MAKE` gates M6.3 and M6.4. Off: today's `adapt_source` and `p_adapt_line` run unchanged. On in Beta first (Q2) |

## The answer in short

1. **When.** Make runs when no Library line fits: an organic department, a default department, or a Library line Root's check refused.
2. **What it reads.** The identity (goal, done-when items, rules) plus three practices in place: the department's rules, the Library's engine and artifact use cases, and the kind's required engines. It does not read the kind's done line, and in version 1 it does not read other departments' workflows.
3. **Levels.** The Make module's level 1 (take a Library engine) and level 2 (shape a new one) are in version 1. Level 3 (probe) is not.
4. **Shape.** Each engine is `{name, does, reads, writes, covers, confidence}`, plus `doubt` and today's `internet`. A plan has the fewest engines that cover every item, usually two to five, and keeps every engine the kind marks required.
5. **Ask.** If any engine is below 0.6, or a required engine cannot serve the goal, Identity asks one question and nothing is registered. Between 0.6 and 0.8 the doubt is shown and nobody is asked. That is at most one question per request and two per cycle.

## The proposal, row by row

**J2B-1 · When Make runs.** `adapt_source` sends a line request to Make in three cases: the department's kind has no line (organic); the kind is default, whose Do line is the Library's fallback and not a fit; or Root's check refused the line, whatever its source (the reshape path `adapt_source` already has). A website department whose words ask for work the website line cannot cover falls into the third case. M5.1 names the uncovered items, Root's check refuses the line (M7.2: every item covered), and the reshape goes to Make. In a default department Make may still return Do alone, at level 1 (J2B-5).

On that reshape path, a kind whose template marks engines required (website: Check, Q12 and M4.4) keeps them: Make takes each required engine at level 1 and keeps it in every reshape, and `c_line_is_engines` refuses a plan that drops one, as Root's check does from M4.4 ('no required engine is left out', M7.2). When a required engine cannot serve an item, Make returns no plan. A game needs a script, and the Library's Check fails any page that carries one. Make answers `cannot` (J2B-4), and the covering posts one conflict to Identity naming the engine and the items. Identity has no rule that settles it, so it asks the owner one question (J2B-7, J2B-8). A plan Root would refuse is never returned.

**J2B-2 · The practices in place it reads.** Only names and use cases go into the request, never whole files (M6.3):

| Candidate | Read? | What goes into the request | Evidence |
|---|---|---|---|
| The department's rules | **Yes** | Every stamped rule with its tag (go, ask, refuse, always). `p_adapt_line` already passes the rules | Tap Rush: the owner's rule 'add no features beyond the three screens' lost to a website condition ('a nav reaches every section'), and the second plan added a nav the owner had ruled out. The plan must answer to the owner's rules, not to a template's checks. |
| The Library's engine use cases | **Yes**, with the artifact use cases | `engines`: each shipped engine template of kind work except Setup (Root's), with its name, use case, reads and writes. `artifacts`: each artifact template a line may write (Brief, Site plan, Pages, Build, Live site, Result), with its name and use case. `taken`: every engine name in use, shipped or born, as names only | Level 1 needs them. Today a shaped line may not use a Library name at all, so a second organic department births 'Facts 2' and 'Site 2' (`d_adapt_line`). The website part of Brew Lab is the Library's own Check and Publish. |
| The kind's required engines | **Yes** | `required`: each engine the kind marks required (website: Check; none for default or organic), with what its check refuses. For Check that is a page with a script, a link to no page, and a page with almost no text (`engine_check`) | Rule 5 (S-06, S-21) and Q12. Without the names, a reshape drops Check, Root's check refuses the plan again (M4.4), and after `J.REPAIRS` the department ends blocked. Without the refusals, Make shapes a game that Check fails. |
| The organisation's earlier registered workflows | **No**, until Learn (FA5) | Nothing | The plan follows the done-when list without any memory. Six runs of the Spark 2026 brief gave first plans of seven or eight workflows of the same shape, and both PRD briefs gave one workflow per section. Reading other departments' lines costs tokens and risks copying a line built for another goal. The prototype's memory was polluted (109 mock playbooks). |
| The kind's done line | **No** | Nothing. The done-when items replace it, and the kind's line survives only as D1 when Root drafted no items (M3.2 offline) | Tap Rush: website checks applied to a game read the score's starting 0 as an invented number, which cost a second round of two fixes. Organic's done line ('what the words asked for is filed, and what goes out is live') says nothing the items do not. |

**J2B-3 · The Make module's levels in version 1.** The site names three levels and two logics (Cynefin and uncertainty) and leaves them empty (gap matrix AD-2). This row fills them in:

| Level | Cynefin domain | What Adaptation does | Version 1 |
|---|---|---|---|
| 1 · Take | Clear: a known practice fits | Takes a shipped Library engine by name, with its template's reads, writes and start. It does so only when the engine's use case fits the goal, and only when what it reads is the Brief or a Library artifact an earlier engine of the plan writes in the form the taken engine reads (the artifact form, below). Born engines are never taken, because their instruction carries another department's words. A required engine of the kind is always taken at this level and kept (J2B-1). | **Yes** |
| 2 · Shape | Complicated: the parts are known, the arrangement is not | Shapes a new engine from Do with its own instruction, as the organic path does today. After Priority's yes and Root's check it is born into the records-home Library, tagged made_by (Q5). | **Yes** |
| 3 · Probe | Complex: nobody knows yet what works | Runs a small try whose result decides the next round. | **No.** A probe pays only when a next round reads its result, which is Pursue (M9), and its lessons are Learn (a non-goal). In version 1, a level-3 situation shows up as an engine Adaptation is not sure of, and J2B-7 turns it into one question. |

**The artifact form.** A level-1 engine reads a Library artifact in the form the Library's own writer files it, and today the artifact's check does not hold that form. Pages is the case that matters. The Library's Check (`engine_check`, `check_rules_of`) reads `_plan.json`: a JSON object whose `pages` list each `{slug, title}` in order, with `index` among the slugs, and optional `site_name`, `tagline` and `palette`. For every planned page it reads `<slug>.html` as a JSON object `{title, body_html}`, where `body_html` is the inside of `<main>`. Only the Library's Write files Pages that way. The Pages template's own check (`pages_have_html`) asks only that each `*.html` is non-empty, and a born engine writing Pages files whole HTML documents (`p_do_page`), with no `_plan.json`. Check then files a failed Build ('no home page'), or fails on the first page it cannot read, and Publish never runs. So a level-2 engine whose artifact a level-1 engine of the plan reads must write that artifact in the reader's form, and code holds it there at the writer:
- `artifacts.py` gains `pages_are_checkable`: `_plan.json` parses and lists its pages, and each planned page's file is JSON with a `title` and a `body_html`. The Pages template names it as its `form`. Script, text and links stay Check's verdicts.
- `_j2_settle` births such an engine with that form. Its page step writes `body_html` (the inside of `<main>`, no script, links only to planned slugs), and `do_file` files `_plan.json` from its planned pages and each page as `{title, body_html}`.
- `do_file` applies the form's check to that writer. Pages in any other form fail where they are written and go back to the writer, and never reach Check as a failed Build.

A shaped engine whose Pages no Library engine reads keeps today's form, so with the flag off nothing changes.

Cynefin's fourth domain (chaotic: act first) is not Make's. It belongs to Identity, acting on the rules. Level 1 is decided by code, never by the model: an engine named after a shipped template is level 1, and any other engine is level 2.

**J2B-4 · The engine shape.** This is what the model returns for each engine:

```json
{"name": "Site", "does": "writes the one page from the design, with the facts exactly as given",
 "reads": "Design", "writes": "Pages", "covers": ["D3", "D4", "D5", "D6", "D7", "D9"],
 "confidence": 0.45, "doubt": "When someone pre-orders, where should the order go? ...", "internet": false}
```

`covers` lists done-when item ids. `confidence` is a number from 0 to 1. `doubt` must be filled when confidence is below 0.8. `internet` is today's field. The covering's check, `c_line_is_engines`, extended, refuses an engine in any of these cases:
- a field is missing;
- confidence is not a number from 0 to 1;
- confidence is below 0.8 and the doubt is empty;
- covers names an unknown id;
- a level-1 engine's reads or writes differ from its template's;
- the plan drops an engine the kind marks required.

In place of engines, Make may answer `{"cannot": {"engine", "items", "why"}}`. The check accepts it only when the engine is one the kind marks required and every item id is known. Anything else is a shape fault.

A refused engine goes back as a shape fault, through today's path (twice at most, then Identity tells the owner). It is never quietly dropped, unlike the prototype's `_atoms_checked`, because dropping an engine would leave items uncovered.

**J2B-5 · Size.** The prompt asks for the fewest engines that cover every item, usually two to five, with every engine the kind marks required included at level 1. One engine is right only when it is the Library's Do and every item is part of one written answer. Split only where a rule or an item needs an artifact of its own, which a later engine or Audit reads by name. Code sets no upper cap (Q11), because Priority's room bounds the plan. A plan of more than five says why in its message. Root's check still refuses more than six until M7.2 lifts that cap.

**J2B-6 · Covers.** An engine covers an item when it answers for it: either its output is where Audit reads the item, or the item restates a rule the engine holds the build to. Before the proposal leaves Adaptation, code checks the following, in the spirit of the prototype's `_plan_checked` and `_lld_gaps`:
- the covers together name every done-when item;
- every engine covers something, or is read by a later engine (a feeder, such as Facts);
- every engine the kind marks required is in the plan, at level 1.

A gap goes back once as a shape fault. M5.1's ledger warning and M7's refusal remain the backstop.

**J2B-7 · The confidence rule (FA1.3).** Confidence is the AI's estimate of how sure it is that this engine, reading what the plan hands it, can make its covered items true without a fact or decision nobody has given. What happens next is decided by code in Adaptation's covering (`adapt_line_offer`), never by the AI:

| Lowest confidence in the plan | What happens | Adaptation's pane (S8) |
|---|---|---|
| 0.8 or more | The proposal goes to Priority. | Nothing extra |
| 0.6 to under 0.8 | The proposal goes to Priority. Each doubt travels with it and appears in the plan tell. | 'Fairly sure', with the doubt under the engine |
| Under 0.6 | Nothing goes to Priority and nothing is registered. Adaptation posts the lowest engine's doubt to Identity, and Identity asks it as one question (an M0.5 ask, `missing: plan`). If the identity already answers it (FI1.2), Identity hands that answer back without asking. | 'Not sure', with 'Asked you' under the engine |
| A `cannot` answer (J2B-1) | Nothing goes to Priority and nothing is registered. Adaptation posts a conflict to Identity naming the required engine and the items. No rule settles it, so Identity asks one question with options built by code (M3.5): set it up as a department done its own way (a Root request with the same words, for your stamp), leave those items out (a done_items ask), or stop. | 'Cannot with this kind', with 'Asked you' |

How it is bounded:
- One question per line request, and two per cycle (the same bound as `J.REPAIRS`).
- Posting the doubt ends the bargain thread before it starts, and the owner's answer opens a new line request with that answer in its words. No bound (4 hops, 15 minutes, spend) runs while the owner thinks.
- If a plan is still under 0.6 after the second answer, it goes to Priority, and the plan tell names the remaining doubt ('going ahead on what you said; still not sure: ...').
- A missing or out-of-range confidence is a shape fault (J2B-4), never a question.

The split between the two questions is this. J2.a asks *what* (goal, items, facts). Under MK-1, facts that were not given are marked to confirm. FA1.3 asks *how*: a decision that changes which engines run or what one of them does. A doubt that is only a missing fact goes the J2.a way: Identity marks it to confirm and asks nothing new.

Why 0.6 and 0.8: no prototype run recorded a confidence, so these are a starting rule, chosen for three properties:
- The fully specified Tap Rush brief, which needed no question in its run, asks nothing.
- A missing decision that changes what an engine sends, or where, asks once before anything runs. Brew Lab's order route is the example.
- Everything in between is shown and not asked, because only a rule asks (S-18).

The rule keeps SM-8 within reach (a median of three or fewer questions and asks from birth to goal). Revisit the numbers in either case:
- more than one in three no-template departments on Beta get a doubt question;
- an item Audit reads as not met traces back to a decision that a plan scoring 0.6 or more never asked about.

**J2B-8 · The question, in Identity's words.** The template is: 'Before I set up the work for {department}: {the doubt, as one question} Unless you say, {what the engine does if it is not told}. Answer in your own words, or say "just do it".' For example: 'Before I set up the work for Brew Lab Website: when someone pre-orders, where should the order go, for example an email to the shop? Unless you say, the form shows the order on screen for the customer to bring to the counter, and sends nothing. Answer in your own words, or say "just do it".'

For a `cannot` answer, the question names what the kind's check refuses and offers the options: 'Before I set up the work for Tap Rush: a website department checks that no page runs a script, and the game needs one. Shall Root set Tap Rush up as a department done its own way, or shall I leave the game out? Unless you say, nothing is set up.'

The question follows these rules:
- It is one question, in plain words.
- No sureness number appears on screen.
- It names no internal parts.
- The fallback never reaches outside.
- 'Just do it' (`JUST_DO_IT`) takes the fallback, and the plan tell names it.

**J2B-9 · Offline.** With no model, today's draft stays (`d_adapt_line`: Facts, then Site; a default department keeps Do). The draft carries no confidence and asks nothing. The plan says it was shaped offline, and its covers map every item to the last engine (M5.1).

## Three worked examples (briefs no Library kind fits)

Done-when items are written as Root would draft them at J1 (M3.2: an id, the text, and the 'how'). All of them are at the target level. 'L1' and 'L2' are the levels in J2B-3. On screen these read 'From the Library' and 'Made for this goal'.

### A · LabSlot, a PRD (default kind; the offline Setup draft picks organic, and both go to Make)

Brief: 'Write a PRD for a web app where students book lab slots... must work on phones. Success: 80% of bookings made without staff help.' Rules (always): every requirement traces to the problem or a must-have; Out of scope lists only things not in the must-have list.

Done-when items, each with its 'how':
- D1: Problem: paper booking and double-booked slots (model);
- D2: Users: students and lab staff, and what each does (model);
- D3: Goals: replaces paper and prevents double-booking (model);
- D4: Requirements name book, cancel and see availability (code);
- D5: Requirements say it works on phones (code);
- D6: Success: 80% of bookings without staff help (code);
- D7: Out of scope holds no must-have (model);
- D8: LabSlot used throughout, and nothing empty or left to confirm (code).

| Engine | Level | Does | Reads > writes | Covers | Confidence |
|---|---|---|---|---|---|
| Requirements | L2 | Lists book, cancel and see availability as R1 to R3, and works-on-phones as R4, each with the problem or must-have it traces to, then lists what is out of scope | Brief > Requirements | D4, D5, D7 | 0.9 |
| PRD | L2 | Writes Problem, Users, Goals, Requirements (R1 to R4 as listed), Success metrics and Out of scope, naming LabSlot throughout | Requirements > PRD | D1, D2, D3, D6, D8 | 0.85 |

Together the covers name D1 to D8, and the lowest confidence is 0.85, so the plan goes to Priority with no question. J2.a has already asked for the name, as the run did. Why two engines and not Do alone: both rules concern the requirements list. Filed on its own, that list is fixed for the PRD engine and gives Audit ids to check traceability against. **In the run**, the work was planned as six section workflows. The same brief's sibling run, also six one-section units, stalled: 'only 1 of 6 sections was written' after 25 calls. The two late questions about a double-booking measure came from the prototype's document rubric. Sutra's Audit reads the done-when items, and a missing measure belongs to J2.a's standard (MK-1).

### B · Tap Rush, a browser game (organic; in a website department Make returns `cannot`, not this plan)

Brief: a 30-second reaction game on one page, with three screens, tap or click only, and the facts 'Tap Rush', 30 seconds, 1 second, 1 point. Rules include: refuse sign-up forms, contact details and prices; no features beyond the three screens; mark to confirm anything not stated.

| Engine | Level | Does | Reads > writes | Covers | Confidence |
|---|---|---|---|---|---|
| Play rules | L2 | Writes the rules of play as numbered lines, with the brief's own numbers: a 30-second round, a circle that lasts 1 second, 1 point a circle, a score starting at 0, tap or click only, three screens | Brief > Play rules | D4 round 30 s, D5 circles score 1, D6 circle lasts 1 s, D8 tap or click only | 0.9 |
| Game | L2 | Builds the three screens and the loop from the rules as one self-contained page: dark background, bright circles, large text, no outside files, nothing beyond the three screens. It goes live after your yes to the first outside step | Play rules > Live site | D1 name, D2 start line and button, D3 score and timer, D7 end screen and Play again, D9 look, D10 no overflow, D11 one file and no forms, contacts or prices, D12 no script errors and links resolve | 0.7. Doubt: 'How often a new circle appears is not given. Unless you say, a new circle appears as soon as the last one goes, marked to confirm.' |

Together the covers name D1 to D12. The lowest confidence is 0.7, so the plan goes to Priority, the doubt is shown ('Fairly sure') and nobody is asked. Check and Publish are not taken, because their use case is a website: Check puts pages into the site's layout, which would add the nav the rules refuse. The plan message names them as left out (Q13). That is allowed only because organic marks no engine required. In a website department the game reaches Make only as a refused Library line, and there Check is required (Q12) and fails any page that carries a script, which the game needs. So Make answers `cannot` with Check and D2, D3 and D12, and Identity asks the one question in J2B-8. No plan without Check is returned. The Play rules artifact is also the source a 'no invented numbers' check needs, since the starting 0 is filed there. **In the run**: a plan of four workflows; a forced nav; all 12 items met; then two fixes for the 0. The run stopped at the account's spend limit.

### C · Brew Lab, design documents first, then the site (website words, but the website line covers no documents, so Root refuses it and the reshape comes here, keeping Check; organic goes straight here)

Brief: 'A one-page website for Brew Lab... Visitors see the menu with prices, the opening hours and where to find the shop, and they can pre-order a coffee for pickup. Write the design docs first.' The brief gives no menu, hours or address. J2.a (MK-1) asks for them, or marks them to confirm, before Adaptation is asked. In the run they were asked at message 177 of 236, after three documents had been written.

Done-when items:
- D1: a PRD with the problem, users, goals, requirements, success at 30 pre-orders a week, and what is out of scope;
- D2: a design naming the page's sections, interactive elements and form fields, each with the requirement it implements;
- D3: the name and the address as text;
- D4: the seven menu items with prices;
- D5: the opening hours;
- D6: the phone and email;
- D7: a pre-order form (name, phone, items, pickup time) that sends the order to the shop;
- D8: no payment field, and the page says to pay at pickup;
- D9: one page that works on phones;
- D10: live at the department's address.

| Engine | Level | Does | Reads > writes | Covers | Confidence |
|---|---|---|---|---|---|
| PRD | L2 | Writes the product requirements from the words: problem, users, goals, requirements R1 to R7, success and out of scope | Brief > PRD | D1 | 0.85 |
| Design | L2 | Writes the page's sections, interactive elements and form fields, each naming the requirement it implements | PRD > Design | D2 | 0.85 |
| Site | L2 | Writes the one page from the design, with the facts exactly as given, in the Pages form Check reads (J2B-3) | Design > Pages | D3, D4, D5, D6, D7, D9 | 0.45. Doubt: the pre-order question in J2B-8 |
| Check | L1, required in a website department | The Library's Check: holds the page to your rules and puts it together as a build | Pages > Build | D8 (the no-payment rule) | 0.9 |
| Publish | L1 | The Library's Publish: puts the checked build live, after your yes to the first publish | Build > Live site | D10 | 0.9 |

Together the covers name D1 to D10. The lowest confidence is 0.45, under 0.6, so nothing goes to Priority and Identity asks the one question in J2B-8. The answer ('email it to hello@brewlab.example') returns as words. Site is shaped again at 0.85 and the plan goes to Priority. Because Check reads what Site writes, Site is born with the Pages form, and `do_file` refuses its Pages in any other form before Check runs. The first send still passes Identity's gate (J2.6). **In the run**, the plan had 31 workflows, one per section per document plus revisions. It took nine cycles, spent the whole budget and ended 'done with open items', with the PRD shipped while its no-invented-facts check still failed. Sutra does not allow that end (Q6). The order route stayed undecided through the design document until the facts question came.

## What M6.3 to M6.5 build from this file

| Step | Builds | Its test |
|---|---|---|
| M6.3 | `adapt_source` adds `practices: {rules, engines, artifacts, required, taken}` (J2B-2) to the line request when the flag is on and the source is shaped | The request carries exactly those five keys: no done line, no other department's workflows, no file text. A website department's `required` names Check |
| M6.4 | `function-prompts/adaptation/make.md` and `p_adapt_line`'s no-template branch ask for the J2B-4 shape, or `cannot`. `c_line_is_engines` checks J2B-4 and J2B-6, including the kind's required engines (from M4.4's `required: true`). `_line_faults` lets a shipped Library engine stand at level 1 with its template's reads and writes. `adapt_line_offer` applies J2B-7 and turns `cannot` into a conflict to Identity, whose ask carries the code-built options. The artifact form (J2B-3): `pages_are_checkable` in `artifacts.py`, `form` on the Pages template, a born writer's page step and `do_file` filing that form, and `do_file` applying it to the writer. The plan ask is recorded by `J.answer`, and Identity sends the answer back as words | Organic and default plans cover their items. A website reshape keeps Check, and a stub that drops it is a shape fault. A stub `cannot` on a website game gives one Identity question with the options and no registration. A stub at 0.45 gives one Identity question and no registration. A stub at 0.7 gives no question, and the doubt appears in the plan. Offline keeps the draft and says so. A shaped engine's Pages, filed in the Pages form, pass the Library's Check and reach Publish. Whole HTML pages from that writer fail `pages_are_checkable` where they are written, and no Build is filed. A shaped Pages writer that no Library engine reads files as today |
| M6.5 | Scenarios on organic and default: shape, bargain, Root's check, run, read | Both reach step 7 with a covering plan |

## Attached: the three runs, their plans and costs

All runs used Sonnet through `claude -p`. Calls and minutes come from `report.json`, and tokens from `calls.jsonl`. No price was recorded, so there is no USD figure. Credits are the prototype's rate-card units. The 'Plan' column lists each workflow with the item numbers it covered.

| Run | Brief | Plan (workflow: covers) | Cost | End |
|---|---|---|---|---|
| j2-20261013-165916 | LabSlot PRD | Problem: 1; Users: 2; Goals: 3; Requirements: 4, 5; Success metrics: 6; Out of scope: 7, 8. One fix after Audit (a double-booking metric) | 1 cycle; 33 calls; 9.1 min; 98 of 200 credits; 592k tokens in, 42k out. Adaptation 3 calls (9% of input), Coordination 7 (21%). 1 counter; 3 questions | Workable at v7 |
| j2-20261014-111512 | Tap Rush game | First plan: Shell: 9 to 12; Start: 1, 2; Play and loop: 3 to 6, 8; End: 7. A plan check (website N8) forced Minimal nav: 12. Two fixes for the score's 0 (website N6) | 2 cycles; 27 calls; 8.5 min; 136 of 200 credits; 536k in, 63k out. Adaptation 4 (13%), builders 9 (42%), Coordination 7 (27%). 0 counters; 0 questions | 12 of 12 items met. The run stopped at the account's spend limit |
| j2-20261016-160511 | Brew Lab, documents first | PRD: six sections plus 2 revisions; design (HLD): six sections plus 3; detailed design (LLD): five sections plus 3; site: Menu: 2; Pre-order: 5, 6; Address: 1, 4; Hours: 3; Layout: 7, 8; plus 1 revision. 31 workflows in all | 9 cycles; 115 calls; 30.1 min; 500 of 500 credits; 3.22M in, 194k out. Adaptation 12 (11%), Coordination 31 (26%), builders 35 (30%). 0 counters; 3 questions | Done with open items: the PRD was shipped with its no-invented-facts check failing |
| j2-20261013-185235 (contrast) | LabSlot PRD again | Six one-section workflows; Problem done, five held | 4 cycles; 25 calls; 10.6 min; 20 of 200 credits; 430k in, 37k out. Adaptation 6 calls (26%) | One section shipped |
| Six Spark 2026 runs (contrast) | One college tech fest brief, run six times | First plans of 7 or 8 workflows of the same shape: one per visitor need, plus a shell | 29 to 37 calls each; 78 to 131 credits | Five done; one done with open items |

In all three main runs, making the plan was the cheap part: Adaptation took 9 to 13 percent of input tokens, against 21 to 27 percent for Coordination. One make step per request, at most two reshapes and one question round is the right budget for Make. On a first pass, the proposed plans need 2 (A), 2 (B) and 4 (C) model calls for the work itself, against 7, 9 and 35 builder calls in the runs.

## Marked

The decision log takes this file as marked. MK-3 reads: 'Take the M6.1 desk spike proposal (design/PRD-FIVE-FUNCTIONS-J2B.md) as marked'. The owner said on 2026-10-23: 'the adaptation here is the logic where you don't need my input'. So the build takes **every row above as keep**, with no owner input.

| Row | Mark | Opens |
|---|---|---|
| J2B-1 When Make runs; a reshape keeps the kind's required engines, or asks | keep | M6.3, M6.4 |
| J2B-2 Practices read: rules, the Library's engine and artifact use cases, and the kind's required engines; not the done line or other departments' workflows | keep | M6.3 |
| J2B-3 Levels 1 and 2 in version 1; level 3 later | keep | M6.4 |
| J2B-4 Engine shape | keep | M6.4 |
| J2B-5 Size: fewest that cover, usually two to five, no code cap | keep | M6.4 |
| J2B-6 Covers | keep | M6.4 |
| J2B-7 Confidence rule: under 0.6, or `cannot`, asks one question; 0.6 to 0.8 shown, not asked | keep | M6.4, M6.5 |
| J2B-8 The question's wording | keep | M6.4 |
| J2B-9 Offline | keep | M6.4 |

The owner can change any row, and a change reopens only the steps that row names. Writing these marks onto the Native site's J2.b and FA1 rows (M6.2) follows the site's own process. This file is the record the build reads. Still pending under C2: the same three briefs run live on Beta with `J2_ADAPT_MAKE` on, to be listed in the build report.

provenance: {author: claude, date: 2026-10-23, inputs: [J2_Prototype 564e3a7 (agents/j2/adaptation.md, j2.py, runs/), sutra engine_runtime.py, engine_defs/website.json, engine-templates/, artifact-templates/], runs: desk read only, review: none by the owner yet, confidence: high on the evidence; the 0.6 and 0.8 thresholds are a starting rule with a stated reversal trigger}
