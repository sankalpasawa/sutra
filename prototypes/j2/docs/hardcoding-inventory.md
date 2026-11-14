# Hard-coding inventory: where code decides instead of an agent

Read-only survey of `prototypes/j2` at commit 3c4c77f2 (branch `agent-tools`). It covers every Python module and the form and type branches in `j2_ui.html`. Test files are left out. Mock-only code is listed at the end but not counted. Line numbers are as of that commit.

## Kinds

| Kind | Meaning |
|---|---|
| NAME | A type, form, section, tool or file name in code or in a prompt code writes |
| FORCED | A rule code puts on an agent's choice: scheduling, who speaks next, stage order, attempt counts, minimums, thresholds, prices. Includes rules code writes into an agent's task as if the agent chose them |
| HIDDEN | Code changes an output or state without telling the agents who judge it |
| KEYWORD | A word list or pattern that decides something. `docs/word-matching-followups.md` rows are included |

Each row also says whether the code should stay or the choice should go to an agent:

- **guardrail:** keep it in code (safety, schema or format checks, sandbox, budgets the user set).
- **decision:** the choice belongs to an agent.

Each row has a group:

- **A:** still fires and wasted a named live run (see the list below).
- **B:** goes away when page and document move to the general form-data path that the folder form uses.
- **C:** other.

Method: four reviewers each read part of the code (j2.py in three ranges, then every other module), and a fifth read the run folders. I checked a sample of line numbers and the largest waste figure (run 165902) against the files. A row is one place in the code, not one rule. Some rules appear twice, once where they are defined and once where they are used, so the counts below overstate the number of distinct rules by roughly 10-15% (moderate confidence).

## Counts

**547 rows.** 357 are decisions and 190 are guardrails.

| Group | Rows | decision | guardrail | NAME | FORCED | HIDDEN | KEYWORD |
|---|---|---|---|---|---|---|---|
| A | 22 | 13 | 9 | 6 | 5 | 2 | 9 |
| B | 196 | 131 | 65 | 130 | 40 | 16 | 13 |
| C | 329 | 213 | 116 | 24 | 198 | 29 | 82 |
| all | 547 | 357 | 190 | 160 | 243 | 47 | 104 |

Some rows have two kinds, for example NAME+KEYWORD, so the kind columns add up to more than the row count.

| File | Rows |
|---|---|
| `j2.py` | 419 |
| `j2_realization.py` | 25 |
| `j2_change.py` | 15 |
| `j2_types.py` | 10 |
| `j2_ui.html` | 9 |
| `j2_artifacts.py` | 8 |
| `j2_studio.py` | 7 |
| `j2_map.py` | 6 |
| `j2_send.py` | 6 |
| `j2_template_lib.py` | 6 |
| `studio.py` | 6 |
| `j2_schema.py` | 5 |
| `j2_check.py` | 4 |
| `j2_server.py` | 4 |
| `j2_agent.py` | 3 |
| `j2_agent_views.py` | 3 |
| `negotiate.py` | 3 |
| `j2_agent_models.py` | 2 |
| `llm.py` | 2 |
| `j2_board.py` | 1 |
| `j2_replay_size.py` | 1 |
| `mock_site.py` | 1 |
| `tools/check_doc_plan.py` | 1 |

## Group A: rules that wasted live runs and still fire

Live runs only (provider claude-cli). Cost in dollars is known only for runs on 2026-11-12. Earlier runs logged `usd` as null. "s" is the sum of the wasted calls' own seconds, not wall-clock time. "Shared" means those calls are already counted in another row.

| # | Rule (where) | Runs and waste | Agent's choice reasonable? |
|---|---|---|---|
| A1 | `assemble_doc` adds a closing "## Assumptions to confirm" section (j2.py:2738-2747, heading at 1436, used at 8377) | **j2-20261112-165902**: HLD cycles 6-9, LLD cycle 11, runbook cycles 13-14. Audit flagged the "seventh heading" each time. 44 calls, 674 s, **$6.96 of the run's $13.40**, 4 Requester pauses. **j2-20261111-095315** cycle 3: 10 calls, 99 s | Yes. Audit, call 72: "W-12's own text had no such section, so something outside the builder's section text appends it" |
| A2 | no-invented-facts: names and numbers (`condition_met` j2.py:1539-1560, `doc_names` 1461) | **j2-20261111-013315** N6 on Sudoku board digits: 18 calls, 483 s. The CSS-drawn-digits workaround then broke 5 items. **165902** H5 on component labels (Gate, Labeller, ...): shared with A1 | Yes. Audit called both false positives |
| A3 | `lld_condition` reads "behaviour" per element (j2.py:2408-2428) | **165902** L3, v1-v2: "E1 (no behaviour)" although every line has "behaviour: ...". Shared with A1 | Yes |
| A4 | `NOT_CHECKABLE` words in done-when items (`_stamp_check` j2.py:5002-5020) | 6 runs, 1 charter retry each (8-14 s): **165902** ($0.036), **011528**, **155605**, **095315**, **013315**, **124718** | Yes. "Requester" and "approving" were product words, some from the template's own section names |
| A5 | at least 3 done-when items (`_stamp_check` j2.py:5009) | **j2-20261112-150327**: 1 call, 9 s, $0.02. Identity split one criterion to reach 3 | Yes |
| A6 | a document workflow must name template sections (`_doc_plan_gaps` j2.py:7061-7103, `_register` 7845-7848, `doc_plan_data` 2610-2638) | **124718**: 8 calls, 96 s. 4 of 8 sections were never written and it shipped incomplete. **012507**: 2 calls, then "Stopped: KeyError: 'Problem'". **165902**: 2 calls, 41 s, $0.19. **155605**: 1 call, 27 s. **095315**: 1 call, 17 s | Yes in 4 runs: the section names were in `outputs`, not `sections`. Unclear in 095315 and the 165902 LLD case |
| A7 | check targets must be named in how (`target_problem` j2.py:678-705) | **j2-20261109-182842**: 3 calls, 140 s (`.level-btn`, `.cell-selected`) | Unclear: made by another workflow that wasn't a declared dependency |
| A8 | `ACTION_GOAL` regex forces a behavior output (j2.py:365) | **182842**: 1 call, 74 s ("highlighted") | Unclear |
| A9 | condition plan regex and generic site conditions (`_plan_gaps` j2.py:6980-6990, `cond_skip` 1379) | N8 "A nav reaches every section ... hero" on a one-screen game. **182842**: 57 s. **j2-20261106-184848**: 31 s | Unclear |
| A10 | `CSS_SAFE` rejects quotes in style values (`parse_style` j2.py:2641-2671) | **184848** W-5: 23 s. **j2-20261103-132506** W-5: 43 s. Font stack `"Segoe UI"` is valid CSS | Yes |
| A11 | builder summary rules (`atom_human_problem` j2.py:386-400, `human_problem` 373) | More than 2 sentences, including "Co." read as a sentence end: **182842** (3 calls, 16 s), **j2-20261110-192347** (1 call, 5 s), **132506** (1 call, 6 s). Summary sent inside a ```json fence read as empty: **184848** (4 calls, 22 s), **192347** (2 calls, 13 s), **132506** (6 calls, 33 s). Whether the fence case is fixed: not verified | Yes |
| A12 | `AGENT_CONTENT` word "counter" marks Requester text as agent talk (j2.py:1823-1826) | **132506**: 1 call, 17 s ("streak counter" is the feature) | Yes |
| A13 | facts-present matches the brief's exact wording (`condition_met` j2.py:1488-1520) | **095315** C2 "missing: [5 brief facts]" for paraphrases. Shared with A1 | Partly |
| A14 | `md_ids` counts a numbered list item as an id definition (j2.py:1062, via `doc_check` 1239 and ids-unique) | **165902** W-8: "1. C8 starts the run." read as a second C8. 1 call, 30 s, $0.08 | Yes |

**Totals for group A (moderate confidence):** about 120 wasted calls across 12 runs. $7.29 is recorded, but only 11-12 runs record cost, so the real total is higher. A1 alone is 95% of the recorded dollars.

### Status on branch `fix-run-blockers`

Each item was replayed on the current code from its run before it was changed; the replay tests use
`fixtures/run-blockers/`.

| # | Replay before the fix | Status |
|---|---|---|
| A1 | 165902 HLD: code's closing section is the 7th heading | Fixed (batch 1): Audit's document prompt says the closing section is added by code from the builders' Assumption: lines and that no builder can change it |
| A2 | 013315 N6 (Sudoku digits): **no longer fires** (stated ranges now source their numbers). 165902 H5 (component labels): fires | Numbers: already fixed. Names: fixed (batch 1): no-invented-facts is a warning in every conditions file |
| A3 | 165902 L3 on LLD v1, v2: fires | Fixed (batch 1): the LLD parser reads "trigger:", "behaviour:" and the field words with or without a colon |
| A6 | 124718, 012507 (Priority dropped "sections"): **no longer fires** (`_carry` restores it). 165902, 155605, 095315 (first plan without "sections"): fires | Priority case: already fixed. First-plan case: fixed (batch 1): the workflow format of a type with sections has a "sections" field; the check stays (hard) |
| A13 | 095315 C2 on v1, v2: fires | Fixed (batch 1): facts-present-all is a warning (split from nothing-to-be-confirmed in website N5 → N5 + N9 and HLD H6 → H6 + H7) |
| A4 | The first charters of 165902, 011528, 155605, 095315, 013315 and 124718: fire | Fixed (batch 2): the NOT_CHECKABLE word list is deleted. Whether an item can be checked is Identity's call, judged by Audit; a fact only the Requester can give goes to to_be_confirmed |
| A5 | 150327's two-item charter for the agent form: fires | Fixed (batch 2): each form declares min_done_when in types.json (page 3, document 3, agent 1), a required field; the validator reads it and Identity's charter format states it |
| A7 | 182842 'undo' and 'conflict-highlight' (`.level-btn`, `.cell-selected`), every recorded version: **no longer fires** (ids that a workflow planned with it creates now count as known) | Already fixed; skipped. Replaying call 10 hits a different rejection (`'.row-0.cell-empty'` read as a charter fact), not in group A |
| A8 | 182842 call 9 'conflict-highlight' ('highlighted'): fires | Fixed (batch 3): the ACTION_GOAL rule is gone from the validator; whether a goal needs a behavior item is Adaptation's call (its atom rules say so), and Audit judges the result |
| A9 | 182842, 184848 N8 plan gap: **no longer fires** (N8's skip_when regex skips games) | Replaced (batch 3): N8 is a warning, a warning never gates a plan, and its skip_when word list is deleted. Side effect: a workflow dropped from the first plan is no longer brought back by the N8 plan flag (work_atoms test) |
| A10 | 184848, 132506 W-5 style (`"Segoe UI"`): fires | Fixed (batch 3): quotes are allowed in pairs in a style value; <, >, {, } and \ are still refused (a value can't close the rule or the style element) |
| A11 | 182842, 192347, 184848, 132506 summaries: **no longer fire** (code cuts a long summary or writes one itself, no re-ask) | Already fixed; skipped. Left: a summary sent in a ```json fence is still dropped and replaced by code's text (no extra call) |
| A12 | 132506 call 131 ('counter'): fires | Fixed (batch 3): only the certain markers (an @agent, an internal id W-/F-/R-/C-n, @Requester in to_agents) send Identity's reply back; word guesses are logged as audience_warning and the reply is kept as written. Kept on the old path: a reply with no to_requester at all (live run of 8 Oct: "@Adaptation Thanks, I'll start building"), so the Requester never ends up with no message |
| A14 | 165902 W-8 ("1. C8 starts the run."): fires | Fixed (batch 3): in a numbered list item an id is defined only in the template's form (bold, or followed by a colon) |

Also in batch 1: groups-covered (P7) and components-have-responsibility (split from H3 into H8) are warnings, as heuristic
conditions. Audit and the planners are told that a warning is a heuristic check that never blocks on its own.

### Not group A
- **Fixed since the run.** grep-count counting CSS and JS mentions (132506), and element-count on a script-built page (182842, 184848, 132506): both fixed in e2a3cabe on 2026-11-11. Missing goal_gap, outputs and completion_check (182842): `_fill_from_plan` now fills them. A heading list stringified into one heading (095315). ids-unique on a metrics table (191311, 19 calls): scoped to the sections a workflow owns.
- **The validator caught a real agent fault.** A reply naming no next speaker (`_usable`): 012507, 095315, 155605, 165902. `to_agents` tagged "@Requester" (`_check_audiences`): 013315, 095315, 165902, 191311. A wrong check type (013315). ids-unique R on a document that only cites R ids (165902 W-7): Adaptation chose that check.
- **No waste found.** 20261102-120445, 20261103-132039, 20261110-200005, 20261110-220236, 20261112-150211, 20261112-164806 (no calls.jsonl). 20261112-120345 is a mock.

## Group C: status on branch `remove-group-c`

Plan and batches: `docs/remove-group-c-plan.md`. Rows are named by their "Where" in the full inventory below (the survey
commit's line numbers); "now" is the line in `j2.py` after the batch. Kept rows are guardrails: safety, budget (code
offers only money it can apply) or valid replies (a fallback for a missing or broken reply).

### Batch 1: Identity

| Row | Status | Now |
|---|---|---|
| `j2.py:3549-3556` `PLAIN_TO_REQUESTER` | Fixed: the "college student" persona, the gallery example options and "No recommendation" are gone. One plain-words style rule stays: everyday words for someone outside the team, no internal terms or function names. Who the Requester and the audience are comes only from the brief and the Requester's answers | `j2.py:4084` |
| `j2.py:5594` `_identity_limit prompt` | Fixed: the second list of banned words and "2 sentences" are gone (the style rule covers them) | `j2.py:6094` |
| `j2.py:5575-5582` `_identity_limit lead` | Fixed: Identity writes the question (a `question` field). It is told what led here as facts (the limit's reason, plus: keep going changed nothing, parts put off twice, parts that don't fit, money used up); no regex on the reason string. Code still builds the options, the amounts and the choices. Code's own question is only the fallback for a reply without one | `j2.py:6069-6105` |
| `j2.py:3862` `_ask_user` 2 sentences | Fixed: no cut before the gap list | `j2.py:4396-4397` |
| `j2.py:3864-3869` `_ask_user` options capped at 3 | Fixed: Identity's options are never cut. Merging several questions into one "Please send these" list is kept: a pause holds one answer (valid replies) | `j2.py:4398-4402` |
| `j2.py:156-157` `AUTO_FINISH, AUTO_SIMPLE` | Fixed: both word lists deleted. A conflict question: Decide for me takes the option Identity marked `plan_option` (stays with the agreed plan), else option 1. A second limit question: the "ship" option from the pause's `choices` | `j2.py:4488-4505`, `5520`, `5580-5586` |
| `j2.py:258-275` `CORE_FACT` fallback, `j2.py:5468` `_gap_rows must_keep`, `j2.py:5637-5652` `_finish_only_option must_keep` | Fixed: `must_keep` reads only the no-errors gate and Identity's `core` marks; a charter without marks has no core items but the gate. The keyword list moved to the mock charter (`MOCK_CORE`) | `j2.py:266`, `2221` |
| `j2.py:4724` `_milestone asks_updates` | Fixed: Identity's intake reply has `email_updates` (true only when the Requester asked for progress updates by email); the charter records it; code reads the charter, not the brief's words. `asks_updates` is used by the mock Identity only | `j2.py:5200`, `5341`, `5379` |
| `j2.py:4889` `_identity_intake` | Fixed: no "1-4 questions" and no "Done-when may not refer to the Requester, Audit, verification, approval or launch" (in `j2.py` and every `templates/*/intake.md`); checkability is Identity's call, judged by Audit (as A4). `agents/j2/identity.md` says done-when items describe what is delivered, not process steps, and a real-file item is added only when the brief or answers ask for a run (the live check's file-copy brief invented one without it). "Don't ask about cost" is kept: Identity can't see the budget | `j2.py:5355`, templates |
| `j2.py:5262-5279` `_identity_hears_requester` unclear answer | Fixed: an answer naming no option is asked again every time, never defaulted to continue or ship. It cannot loop: each re-ask is a Requester pause (status waiting) that only a new Requester message resumes, and Decide for me answers with a bare option number, which always names an option. "Continue becomes drop when it isn't offered" is kept (budget) | `j2.py:5753-5766` |
| `j2.py:79` `LIMIT_ADD`; `j2.py:1804-1807` `DECIDE_FMT, DECIDE_RULE`; `j2.py:3870` budget options stripped; `j2.py:5046` resolve fmt; `j2.py:5511-5590`, `5559-5574` limit options; `j2.py:4348-4377` stage options; `j2.py:5619-5625` one option applied | Kept: budget. Only code offers money, with amounts it can apply |
| `j2.py:5097-5103`, `5109` resolve fallback question and defaults; `j2.py:5171-5175` approval fallback; `j2.py:4978-4984` stamp retry then accepted | Kept: valid replies |
| `j2.py:4044` stuck; `j2.py:5709-5719` same failure twice; `j2.py:5531` stale; `j2.py:5761-5766` workable decides done | Kept: safety and loop bounds |
| `j2.py:4807-4818` change request keeps items word for word | Kept: item numbers are tied to item text (`charter_items`); rewording would break them |
| `j2.py:154` `AUTO_ASSUME` | Kept: the Requester's own Decide-for-me answer, not Identity's |
| `j2.py:4340`, `4387-4390` `_stage_gate`, `_stage_decision`; `j2.py:1942-2010` `parse_decision` | Batch 1b |
| `j2.py:1828` `PLAIN_WORDS`; `j2.py:1915-1926` `requester_words`; `j2.py:1928-1939` `to_requester` | Later batch: hidden rewrites |
| `j2.py:5356-5360`, `5368-5376` routing after a drop or a limit answer | Batch 2 (Coordination) or the batch-5 proposal |

## Full inventory


### `j2.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2.py:73-74` | FORCED | `BUDGET, BUDGET_CAP` | Starting budget 100 and the most Requester approvals can raise it to (2x) | Priority, Identity | guardrail | C |
| `j2.py:75` | FORCED | `MAX_ATTEMPTS` | Two disagreeing agents get 4 exchanges, then Identity rules; also shown in state as max_exchanges | Adaptation, Priority, Coordination, Audit, Identity | guardrail | C |
| `j2.py:76-77` | FORCED | `BARGAIN_MINUTES, BARGAIN_CALLS` | J2.c bargain ends after 15 minutes or 8 AI calls, then goes to Identity | Adaptation, Priority | guardrail | C |
| `j2.py:78` | FORCED | `MAX_CYCLES` | Six plan-build-audit loops, then Identity must ask the Requester | Identity | guardrail | C |
| `j2.py:79` | FORCED | `LIMIT_ADD` | "Keep working" adds 30 credits when Identity gives no budget_needed (used at 5524) | Identity, Requester | decision | C |
| `j2.py:81-83` | FORCED | `MAX_LESSONS, MAX_PLAYBOOKS` | Adaptation reads at most 5 lessons and 2 playbooks, picked by code | Adaptation | guardrail | C |
| `j2.py:86-93` | NAME | `RUBRIC` | Fixed 7-item page design rubric in code (R-1..R-7); every item must pass for workable | Audit | decision | B |
| `j2.py:95` | NAME | `WORKABLE_OUTCOME` | Done message hard-codes "the site is workable" and the render check | Identity | decision | B |
| `j2.py:97` | FORCED | `MAX_TURNS` | 30 agent turns per cycle (floor of _turn_cap) | all functions | guardrail | C |
| `j2.py:103` | NAME | `SITE_WARN_BYTES` | Warns when a page is over 60 KB (used 8431) | builders | guardrail | B |
| `j2.py:115-121` | FORCED | `ROUTES` | Who may hand the turn to whom; only Identity may reach the Requester | all functions | guardrail | C |
| `j2.py:124-126` | FORCED | `add_workflow_agent` | A builder may only hand the turn to Coordination | builders | guardrail | C |
| `j2.py:147` | KEYWORD | `TO_USER` | A message tagged @requester/@user from a non-Identity agent is redirected to Identity | all functions | guardrail | C |
| `j2.py:152-153` | FORCED | `AUTO_ASK, AUTO_CAP` | Decide-for-me never answers send_confirm; after 6 answers the next question waits | Requester proxy | guardrail | C |
| `j2.py:154` | FORCED | `AUTO_ASSUME` | Canned Requester answer "go with sensible choices, list assumptions" when there are no options | Identity | decision | C |
| `j2.py:156-157` | KEYWORD | `AUTO_FINISH, AUTO_SIMPLE` | Decide-for-me picks a conflict or limit option by words (skip, without, finish, as it is) (3965-3968) | Identity, Requester proxy | decision | C |
| `j2.py:191` | FORCED | `ENVELOPE_DEFAULTS` | model_call_limit 2 and retry_limit 1 when Priority leaves them out (7881) | Priority, builders | decision | C |
| `j2.py:201-222` | FORCED | `RATES_ON, load_rates, price` | Rate-card prices replace Adaptation's estimate; the card is picked from the type's cost.card | Adaptation, Priority | decision | C |
| `j2.py:225` | NAME | `RATES_DOC` | Document pricing reads the "rates_prd" card by name (4290) | Adaptation, Priority | decision | B |
| `j2.py:229` | FORCED | `RATES_DEED` | Fixed price per send deed from rates.json | Priority | decision | C |
| `j2.py:246-253` | KEYWORD | `item_kind, item_min` | Minimum rate-card part per done-when item read from its words (followup #1) | Adaptation, Priority | decision | C |
| `j2.py:258-275` | KEYWORD | `NO_ERRORS_GATE, CORE_FACT, must_keep` | Items that can't be dropped for budget: gate regex, plus core-fact keywords/site_name when core_items is missing | Identity, Priority | decision | C |
| `j2.py:259` | FORCED | `GATE_TEXT` | Code writes a fixed JS-errors/overflow/links done-when item into the charter at J2.a (4939) | Identity | guardrail | B |
| `j2.py:263` | KEYWORD | `BUDGET_TALK` | Rejects an Adaptation POLICY_QUESTION about budget, detected by words (7235; followup #2) | Adaptation | decision | C |
| `j2.py:306-319` | NAME | `EXAMPLE_WORKFLOW` | Page-only example (Contact section, #contact, form part) in Adaptation's plan prompt (6039) | Adaptation | decision | B |
| `j2.py:321-329` | FORCED | `ATOM_FIELDS, atom_missing` | Every atom needs goal, constraints, context, how, expected_output and verification | Adaptation | guardrail | C |
| `j2.py:335-337` | NAME | `CHECK_TYPES, DOC_CHECK_TYPES, PAGE_FILE` | Check types and file name read through form("page")/form("document"); "index.html" by name | Adaptation, builders | decision | B |
| `j2.py:338-339` | NAME | `COUNTED, NAMED_TESTS` | Hard-coded check names: counted types and only 3 named tests allowed (847) | Adaptation | guardrail | B |
| `j2.py:340` | FORCED | `MAX_CHECK_ATTEMPTS` | Each atom (and the folder stage) gets 3 build attempts, whatever Priority's envelope says | builders, Coordination, Priority | decision | C |
| `j2.py:342-346` | KEYWORD | `SPECIFIC, FACT_VALUE` | A goal with a number/price/time/email must have a facts-present or named-test check (869) | Adaptation | decision | C |
| `j2.py:349` | KEYWORD | `NEGATED` | Negation words in a check label allow expect 0 against the label's number (867) | Adaptation | decision | C |
| `j2.py:359-362` | KEYWORD | `ID_RANGE, RC_RANGE, NAME_WITH_DIGIT, MAX_RANGE_IDS` | Regex reads id ranges from how text to decide which ids the builder was told to create | Adaptation | decision | C |
| `j2.py:365` | KEYWORD | `ACTION_GOAL` | Action words in a goal force a behavior expected-output item (872) | Adaptation | decision | A (A8) |
| `j2.py:368-370` | KEYWORD | `DATE_RULE, DATE_CONTROL` | A date-rule goal must set a date control in its steps (753) | Adaptation | decision | C |
| `j2.py:373` | FORCED | `human_problem` | A builder's human_output must be 1-3 sentences and at least 5 words | builders | guardrail | A (A11) |
| `j2.py:386-400` | KEYWORD | `INTERNAL, atom_human_problem` | Atom human_output must be 1-2 sentences, with no ids, selectors or "units" | builders | guardrail | A (A11) |
| `j2.py:438` | HIDDEN | `fallback_human` | Code cuts or rewrites a builder's human_output (8594); logged only to autofix.json | builders, Audit | decision | C |
| `j2.py:446-462` | NAME | `build_agent_output` | agent_output names "site/v{n}.md\|html", "site/index.html" and reads headings with h1-3 or ## regex | builders, Audit | guardrail | B |
| `j2.py:488-538` | FORCED | `SANDBOX_DENY_WRITE, sandbox_rerun` | Test rerun in sandbox: no network, writes only in a copy of the folder | builders | guardrail | C |
| `j2.py:645-666` | KEYWORD | `css_problem` | Each part of a compound selector must be named in how/constraints; a digit name found in the charter is rejected (#7) | Adaptation | decision | C |
| `j2.py:668` | KEYWORD | `page_names` | Quoted strings in page scripts count as known ids/classes for later checks | Adaptation | decision | C |
| `j2.py:678-705` | KEYWORD | `target_problem, LINK_TARGET` | Check targets must be ids/classes told in how; link addresses are allowed; charter values are rejected (#7) | Adaptation | decision | A (A7) |
| `j2.py:707-757` | FORCED | `allowed_numbers, behavior_problems` | expect-number may only use charter/answer/step numbers; step cap; expect-changed needs wait first | Adaptation | guardrail | C |
| `j2.py:760` | HIDDEN | `fixed_step` | Validator rewrites "expect-text X" to "expect-visible X" (7163); autofix.json only | Adaptation, Audit | decision | C |
| `j2.py:781-799` | HIDDEN | `UNTOLD, untold_selector` | Parses the validator's own wording and adds a "Create the element(s)" constraint to the atom (7169-7174) | Adaptation, builders | decision | C |
| `j2.py:835` | FORCED | `check_problems lld-slice` | lld-slice checks are written into atoms by code at registration (7972), never by Adaptation | Adaptation, Audit | decision | B |
| `j2.py:843-846` | FORCED | `check_problems` | section-not-empty expect at least 1; ids-unique target must be 1-3 capitals | Adaptation | guardrail | B |
| `j2.py:860-868` | KEYWORD | `check_problems` | A number in a counted check's label must equal its expect; 360/1280 ignored for tap-targets | Adaptation | decision | C |
| `j2.py:954-961` | NAME | `run_check grep-count` | grep-count reads PAGE_FILE when the check names no file | builders, Audit | guardrail | B |
| `j2.py:1081` | HIDDEN | `split_heading_lists` | Splits list-target heading checks into one per heading (7156); autofix.json only | Adaptation, Audit | guardrail | B |
| `j2.py:1143` | HIDDEN | `cover_expected` | Code appends a derived check for every expected-output item no check covers | Adaptation | guardrail | C |
| `j2.py:1162` | KEYWORD | `facts_to_headings` | A short facts string with no digit that isn't in the charter becomes a heading check (#8) | Adaptation, Audit | decision | C |
| `j2.py:1213` | HIDDEN | `corrected_check` | Rewrites a failed doc check's target (drops "section", punctuation, fuzzy fact match) so it passes (6968, 10092) | Audit, Adaptation | decision | B |
| `j2.py:1239` | NAME | `doc_check` | Document-only check runner (markdown headings, words, ids) | builders, Audit | guardrail | A (A14) |
| `j2.py:1333` | NAME | `export_docx` | Document export hard-coded as .docx | Identity | guardrail | B |
| `j2.py:1367` | KEYWORD | `TBC_WORDS` | "to be confirmed"/TBC anywhere in the document fails nothing-to-be-confirmed (1561) | Audit, Identity | decision | C |
| `j2.py:1379` | KEYWORD | `cond_skip` | Regex from conditions/<type>.json on statement/business_type decides whether a condition applies | Audit | decision | A (A9) |
| `j2.py:1435-1436` | NAME | `ASSUMPTION, ASSUMPTIONS_HEADING` | "Assumption:" lines are exempt from no-invented-facts; "Assumptions to confirm" heading by name | builders, Audit | decision | A (A1) |
| `j2.py:1437` | KEYWORD | `PRACTICE` | "Recommended practice:" lines allowed only when the type's data says so | builders | guardrail | B |
| `j2.py:1438` | KEYWORD | `NO_ACTIONS` | groups-covered accepts only the exact phrase "X have no actions in this version" | builders, Audit | decision | B |
| `j2.py:1439` | KEYWORD | `WINDOW` | Time-word regex decides whether a numeric metric states a measurement window | builders, Audit | decision | B |
| `j2.py:1450` | HIDDEN | `VERSION_NOTE` | Code-written "Version n:" notes inside sections, removed before checks | Audit | decision | B |
| `j2.py:1461` | KEYWORD | `doc_names` | Capitalised words count as invented proper names; skip list built from every type's section words | builders, Audit | guardrail | A (A2) |
| `j2.py:1479` | KEYWORD | `user_groups` | With no user_groups, splits "users" by comma/and into groups | Identity, Audit | decision | C |
| `j2.py:1500` | FORCED | `condition_met sections-present` | Every required section must be present with at least min_words | builders | guardrail | B |
| `j2.py:1512-1520` | NAME | `condition_met facts-present-all` | With no facts list, falls back to product_name/site_name as the only fact | Identity, Audit | decision | A (A13) |
| `j2.py:1522-1530` | NAME | `condition_met groups-covered` | Defaults to sec_name("prd","requirements"); plural "s" stem match | Audit | decision | B |
| `j2.py:1531-1538` | NAME | `condition_met metric-window` | Defaults to sec_name("prd","success_metrics") | Audit | decision | B |
| `j2.py:1539-1560` | KEYWORD | `condition_met no-invented-facts, doc_numbers, source_numbers` | Every number, phone, email and name must come from the charter/answers; ranges over 100 aren't expanded | builders, Audit | guardrail | A (A2) |
| `j2.py:1576-1592` | NAME | `chain-ids, components-have-responsibility` | HLD/LLD-specific code checks (C1.. ids, responsibility at least 3 words) | builders, Audit | decision | B |
| `j2.py:1608-1631` | NAME | `_page_parses, _no_js_errors, _no_overflow` | Page render conditions; an unrendered page fails | builders | guardrail | B |
| `j2.py:1633-1646` | KEYWORD | `TEL, WA_ME, _links_well_formed` | tel: and wa.me links must match fixed regexes (WhatsApp named in code) | builders | guardrail | B |
| `j2.py:1648` | FORCED | `_forms_have_destination` | Every form needs a submit control and an action | builders | guardrail | B |
| `j2.py:1660-1680` | KEYWORD | `_nav_and_main_action` | "hero" in an id/class (else the first header/section) is the hero; the nav must reach every section | builders, Audit | decision | B |
| `j2.py:1688-1716` | NAME | `mock_atom` | Also code's cheapest-fit atom (7259): index.html, .order-form, R-6 tap check for a "form" part | Adaptation | decision | B |
| `j2.py:1730` | NAME | `SITE_FILES` | Page file names that never count as artifact outputs | Adaptation | decision | B |
| `j2.py:1733` | KEYWORD | `FILE_PATH, is_artifact` | The shape of the outputs strings decides that a workflow is a file workflow (#12) | Adaptation | decision | C |
| `j2.py:1804-1807` | FORCED | `DECIDE_FMT, DECIDE_RULE` | Agents may not offer add-budget/drop/finish options; code asks with its own amounts | Identity, Adaptation | decision | C |
| `j2.py:1811` | KEYWORD | `BUILT_CLAIM` | Identity saying "built" before anything passes is an invalid move (5606) | Identity | guardrail | C |
| `j2.py:1823-1826` | KEYWORD | `AGENT_CONTENT, USER_CONTENT` | Audience-mix regexes on Identity's reply (USER_CONTENT names site/shop/store) | Identity | guardrail | A (A12) |
| `j2.py:1828` | HIDDEN | `PLAIN_WORDS` | Rewrites Identity's Requester text (units to work credits, cycle to round, drops "(estimated)") | Identity | guardrail | C |
| `j2.py:1914` | KEYWORD | `NUMBER_ASK` | Doc fact question with number words gets "over what time..." appended by code (5407) | Identity | decision | B |
| `j2.py:1915-1926` | HIDDEN | `INTERNAL_ID, requester_words` | Drops whole sentences and brackets naming internal ids, plus "Alternatives:" sentences | Identity | decision | C |
| `j2.py:1928-1939` | HIDDEN | `to_requester` | Cuts Identity's text to 3 statements and 1 question; removes numbered lines | Identity | decision | C |
| `j2.py:1942-2010` | KEYWORD | `NEGATION, OPTION_WORDS, ONLY_PICK, affirmed, parse_decision` | Code reads the Requester's answer as continue/drop/ship/stop, an amount and dropped items (substring match) | Identity | decision | C |
| `j2.py:2065-2108` | NAME | `lld_slice, lld_check` | The LLD is the page's spec; code checks the page against an LLD slice | builders, Audit | decision | B |
| `j2.py:2347-2401` | KEYWORD | `parse_hld, parse_lld, doc_agent_output` | Regex parse of C1/S1/E1/F1 lines under sec_name("hld"/"lld") sections; kind "prd"/"hld"/"lld" by name | builders, Audit | decision | B |
| `j2.py:2408-2428` | NAME | `lld_condition` | LLD-only checks: unique ids and selectors, complete elements and fields | builders, Audit | guardrail | A (A3) |
| `j2.py:2502-2521` | FORCED | `stage_goal` | Code writes the HLD/LLD charter: one item per section, all core, "Every item traceable to the PRD" | Identity | decision | B |
| `j2.py:2529-2535` | FORCED | `SITE_FIRST, SITE_LATER` | Tells Identity to ask now for menu items, prices, hours, address and form fields | Identity | decision | B |
| `j2.py:2536` | NAME | `DOC_NOTE` | Every document prompt says "read site as document; no style guide; Audit uses the document rubric" (3586) | all functions | decision | B |
| `j2.py:2541-2542` | NAME | `WF_TYPES, WF_KINDS` | Plan format lists the page form's check types; string-replaced for documents (3284) | Adaptation, Priority | decision | B |
| `j2.py:2548` | NAME | `LEGACY_OUTPUT` | A record without an output type is "website" (old runs, lessons 2924, workable 2784) | Adaptation, Audit | guardrail | B |
| `j2.py:2569` | NAME | `is_page` | form == "page" branches (callers 2784, 3090, 4287, 4445, 4727, 5496, 9588...) | all | decision | B |
| `j2.py:2575-2585` | NAME | `_data_type` | export == "docx" maps to export_docx; mock entries map to mock_* functions by name | Identity | decision | B |
| `j2.py:2610-2638` | FORCED | `doc_plan_data` | Each section written by exactly one workflow; one heading and one not-empty check each; per-section prices, multi-section at least the sum | Adaptation, Priority | decision | A (A6) |
| `j2.py:2641-2671` | FORCED | `STYLE_FMT, parse_style` | Fixed style-guide schema (hex palette keys, fonts, Google Fonts URL only) for the first page builder | builders | guardrail | A (A10) |
| `j2.py:2673` | NAME | `style_css` | Injects .j2-btn, .j2-btn-secondary, .j2-card and --j2-* variables into every page | builders | guardrail | B |
| `j2.py:2698` | NAME | `assemble` | Page assembled from J2-marked sections inside a fixed html skeleton | builders | guardrail | B |
| `j2.py:2707-2722` | FORCED | `parse_section` | ```section/```head blocks only; a form without a submit button rejects the reply | builders | guardrail | B |
| `j2.py:2725-2735` | FORCED | `parse_doc` | Markdown only, no HTML, must start with a "## " heading | builders | guardrail | B |
| `j2.py:2738-2747` | HIDDEN | `assemble_doc` | Orders sections by the type's order and appends an "Assumptions to confirm" section Audit never sees as a decision | Audit, builders | decision | A (A1) |
| `j2.py:2750-2767` | KEYWORD | `FORCED_NOTES, forced_note` | Test switch J2_FORCE_AUDIT_FAIL picks a fake finding by item words (menu, hours, map, form, loyalty) | Audit | guardrail | C |
| `j2.py:2773-2797` | FORCED | `workable` | Code's J2.h verdict: every item, rubric, condition and render check passes; Requester-accepted ids skipped | Identity | guardrail | C |
| `j2.py:2784` | NAME | `workable` | Document branch: no render check, and accepted rubric/condition ids aren't skipped | Identity | decision | B |
| `j2.py:2800` | HIDDEN | `check_summary` | For a document, replaces Identity's words to the Requester with code-written results (5605) | Identity | decision | B |
| `j2.py:2821` | FORCED | `failure_signature` | The same failure signature twice in a row triggers the limit question | Identity | guardrail | C |
| `j2.py:2901-2911` | KEYWORD | `relevant_playbooks` | Same business_type only (none for "business"), ranked by word overlap with the brief | Adaptation | decision | C |
| `j2.py:2914-2931` | KEYWORD | `WORD, relevant_lessons` | Lessons picked by 4-letter-word overlap, filtered to the output type (website by default) | Adaptation | decision | C |
| `j2.py:3067-3090` | NAME | `saved_page, saved_output, run_page` | A saved run with site/v*.html and no record is a "website" page type | UI | guardrail | B |
| `j2.py:3093-3114` | NAME | `output_info` | Exported files named file[:-3]+".docx" and "{kind}.md" | UI | guardrail | B |
| `j2.py:3271` | NAME | `_apply_output self.doc` | form == "document" sets self.doc (prompts, check types, files, export; 77 uses) | all | decision | B |
| `j2.py:3284-3288` | NAME | `_apply_output doc_fmt` | String-replaces page prompt text ("R-6", steps, count) for documents; page ATOM_RULES are the default | Adaptation, Priority | decision | B |
| `j2.py:3310` | HIDDEN | `_accept_open` | Failing items the Requester finished with are skipped by workable() from then on; event log only | Audit, Identity | guardrail | C |
| `j2.py:3325-3327` | FORCED | `_turn_cap` | Turns per cycle = max(30, 10 + 4 x workflows registered this cycle) | all functions | guardrail | C |
| `j2.py:3391` | FORCED | `_raise_budget` | A Requester-approved raise is capped at BUDGET_CAP | Identity | guardrail | C |
| `j2.py:3414-3417` | HIDDEN | `post` | Identity's Requester text passes through to_requester and _requester_noun before it is shown | Identity | decision | C |
| `j2.py:3456-3460` | FORCED | `state blind` | Identity's state leaves out budget, rate card and costs | Identity | guardrail | C |
| `j2.py:3480-3486` | FORCED | `state rate_card` | Writes "estimated_resources.money is ignored", keyword item minimums and "one fix part per finding" into the state | Adaptation, Priority | decision | C |
| `j2.py:3549-3556` | FORCED | `PLAIN_TO_REQUESTER` | Requester is "a college student"; banned terms, example options (gallery), "No recommendation" | Identity | decision | C |
| `j2.py:3559-3664` | HIDDEN | `REPLY_DEFAULTS, _check_audiences` | A mixed-audience reply is retried once, then replaced with canned text | Identity | guardrail | C |
| `j2.py:3670` | NAME | `_read_summary` | Call summary labels the charter by site_name, else "site" | none (record) | decision | B |
| `j2.py:3730-3785` | FORCED | `_builder_tools, _tool_record, _tool_fault` | Tools only with J2_AGENT_TOOLS=1 and every setting set; an outside write or a limit breach stops the build | builders | guardrail | C |
| `j2.py:3788` | FORCED | `_pick` | An off-route "next" is replaced by a fallback agent that code picks | all agents | guardrail | C |
| `j2.py:3808-3816` | FORCED | `_say (repeat)` | A message identical to the agent's last one is not posted, and Identity takes the turn | Adaptation, Priority, Coordination | decision | C |
| `j2.py:3818` | KEYWORD | `_say TO_USER` | Text containing "@requester/@user" reroutes the whole message to Identity | Adaptation, Priority, Coordination, Audit | guardrail | C |
| `j2.py:3856-3858` | HIDDEN | `_ask_user to_requester/requester_words/_requester_noun` | Code rewrites Identity's question, options and words before the Requester sees them | Identity | decision | C |
| `j2.py:3862` | FORCED | `_ask_user` | Identity's message is cut to 2 sentences when a code gap list follows | Identity | decision | C |
| `j2.py:3864-3869` | FORCED | `_ask_user` | Several questions merge into one "Please send these" list; their options are dropped; options capped at 3 | Identity | decision | C |
| `j2.py:3870` | FORCED | `_ask_user` | Budget options are stripped from every question except the code-built limit question | Identity | decision | C |
| `j2.py:3899` | KEYWORD | `_override drop` | Owner "drop <words>" removes every done-when item that contains the words as a substring | Identity, Audit | guardrail | C |
| `j2.py:3945-3950` | FORCED | `_auto_pick AUTO_CAP/AUTO_ASK` | Decide-for-me stops after J2_AUTO_CAP answers and never answers send_confirm | Requester | guardrail | C |
| `j2.py:3953-3971` | KEYWORD | `_auto_choice AUTO_SIMPLE/AUTO_FINISH` | Auto-answer picks an option by words ("keep it simple", "without", "finish", "as it is"), else the first | Requester | decision | C |
| `j2.py:4044` | FORCED | `_run stuck` | Two cycles registering nothing force Identity's limit question | Identity, Adaptation | decision | C |
| `j2.py:4048` | FORCED | `_run MAX_CYCLES` | After J2_MAX_CYCLES cycles Identity must ask the Requester | Identity | guardrail | C |
| `j2.py:4050` | FORCED | `_run out_of_budget` | Credits left below the cheapest rate-card part force the limit question | Identity | guardrail | C |
| `j2.py:4064-4068` | FORCED | `_run _turn_cap` | Per-cycle turn cap forces the limit question; J2.h after an audit is exempt | Identity | guardrail | C |
| `j2.py:4099` | NAME | `_run` | Export runs only when self.doc | none | decision | B |
| `j2.py:4134-4146` | NAME | `CHARTER_FMT` | Default charter prompt: site_name; core = name, location, contact, prices, hours, ordering, no-errors | Identity | decision | B |
| `j2.py:4152` | NAME | `_fact_problems` | Charter-facts-in-brief check skipped for documents | Identity | guardrail | B |
| `j2.py:4173-4192` | FORCED | `_plan_stages` | form=="document" types run first, then sends, then pages, whatever order the planner gave | Adaptation (planner) | decision | B |
| `j2.py:4175` | KEYWORD | `_plan_stages detect_deeds` | Email/Slack send stages added from the brief's words | Adaptation (planner) | decision | C |
| `j2.py:4177-4185` | KEYWORD | `_plan_stages names_other` | Warns about a named recipient by words; a send without a document is refused, naming PRD/HLD/LLD | Requester | guardrail | C |
| `j2.py:4187` | FORCED | `_plan_stages` | With no document chosen, only the first page type is kept | Adaptation (planner) | decision | B |
| `j2.py:4229` | FORCED | `_deliverables j2_types.create` | A type the planner invents is always created as a document | Adaptation (planner) | decision | B |
| `j2.py:4242` | FORCED | `_deliverables` | A plan naming no known type after one revision stops the run | Adaptation (planner) | guardrail | C |
| `j2.py:4282-4294` | FORCED | `_stage_cost` | Stage minimum price: page essentials, doc_section*(n-1)+requirements_section, or deed rate | Priority | decision | B |
| `j2.py:4340` | FORCED | `_stage_gate` | In chain order, the first stage that doesn't fit blocks every later stage | Identity, Requester | decision | C |
| `j2.py:4348-4377` | FORCED | `_stage_gate` | Code writes the stage options: add (≤BUDGET_CAP), leave out, finish only if documents exist | Identity | decision | C |
| `j2.py:4387-4390` | FORCED | `_stage_decision` | An unparseable stage answer defaults to continue, else drop | Identity, Requester | decision | C |
| `j2.py:4423-4429` | NAME | `_stages_finished` | Code writes "Your design documents are ready"/"Your document is ready" and the outcome | Identity | decision | B |
| `j2.py:4445-4452` | NAME | `_begin_stage` | Page after docs: only chain["lld"] is a blueprint; WF_FMT/GRANT_FMT patched with lld_sections | Adaptation, Priority | decision | B |
| `j2.py:4454-4460` | FORCED | `_begin_stage stage_goal` | Code writes the doc stage charter and marks every done-when item core | Identity | decision | B |
| `j2.py:4462` | NAME | `_begin_stage` | The "written from the PRD/HLD" note is chosen by kind=="hld" | none | decision | B |
| `j2.py:4466` | FORCED | `_deed_stage` | Send stage: code builds the workflow, message, price and check; no agent sees it | Adaptation, Priority, Audit | guardrail | C |
| `j2.py:4498` | FORCED | `_start_work/_folder_stage` | Folder form: code registers one workflow; no Adaptation, Priority or Audit | Adaptation, Priority, Audit | decision | C |
| `j2.py:4551` | FORCED | `_folder_stage` | Folder workflow price = sum of the form's essentials rates | Priority | decision | C |
| `j2.py:4556-4566` | FORCED | `_folder_stage MAX_CHECK_ATTEMPTS` | Builder gets 3 attempts; envelope call/retry limits set from that constant | Builder | decision | C |
| `j2.py:4567-4575` | FORCED | `_folder_stage task` | Code dictates exact files, test command, word-for-word copying of charter fields | Builder | decision | C |
| `j2.py:4603` | FORCED | `_folder_stage` | On pass, code posts Identity's "ready" message and the Done outcome | Identity, Audit | decision | C |
| `j2.py:4670` | NAME | `GOAL_TAGS` | Milestone tags by name prd/hld/lld; a page by its label | none | decision | B |
| `j2.py:4684` | KEYWORD | `_identity_send_confirm` | Regex yes/y/ok/sure/1 allows live email; anything else means no | Identity | guardrail | C |
| `j2.py:4724` | KEYWORD | `_milestone asks_updates` | Milestone emails turned on by the brief's words | Identity | decision | C |
| `j2.py:4727-4750` | NAME | `_milestone` | Doc file vs "site/index.html", site_name/product_name, summary taken from the first "##" section | none | decision | B |
| `j2.py:4731` | FORCED | `_milestone` | Email skipped when credits left < send_email rate | Priority | guardrail | C |
| `j2.py:4781-4790` | NAME | `_deeds_finished` | Code writes the closing "design documents"/"document is ready" text | Identity | decision | B |
| `j2.py:4807-4818` | FORCED | `_identity_intake change` | Code rules: one new item per outcome; existing items, statement, audience kept word for word | Identity | decision | C |
| `j2.py:4867-4891` | NAME | `_identity_intake default prompt` | Page intake: business examples (florist, photographer, dental clinic), "site", SITE_FIRST/SITE_LATER | Identity | decision | B |
| `j2.py:4889` | FORCED | `_identity_intake` | Done-when may not mention Requester/Audit/approval/launch; 1-4 questions; no cost questions | Identity | decision | C |
| `j2.py:4892` | FORCED | `_identity_intake last` | After one reply with neither questions nor charter: "record the charter now", then the run stops | Identity | guardrail | C |
| `j2.py:4923-4929` | FORCED | `_identity_intake _fact_problems` | Unfound facts get one re-ask, then code drops them from the charter | Identity | guardrail | C |
| `j2.py:4933-4936` | NAME | `_identity_intake` | Doc: site_name="Document", business_type overwritten with the type name, hld/lld get stage_goal | Identity | decision | B |
| `j2.py:4939` | KEYWORD | `_identity_intake NO_ERRORS_GATE` | An item matching the no-errors regex is replaced by the fixed page GATE_TEXT | Identity, Audit | decision | B |
| `j2.py:4960` | FORCED | `_identity_intake charter_drop` | Code pauses to ask the Requester about dropped_from_brief items | Identity | guardrail | C |
| `j2.py:4966` | FORCED | `_identity_intake _pick` | After the charter, only Adaptation may speak next | Identity | guardrail | C |
| `j2.py:4978-4984` | FORCED | `_identity_intake` | A charter failing the stamp check gets one retry, then is accepted anyway | Identity | decision | C |
| `j2.py:5002-5020` | KEYWORD | `NOT_CHECKABLE/_stamp_check` | Item words (approve, launch, verify, audit, requester) reject the charter (followups #9) | Identity | decision | A (A4) |
| `j2.py:5009` | FORCED | `_stamp_check` | The charter needs at least 3 done-when items | Identity | decision | A (A5) |
| `j2.py:5046` | FORCED | `_identity_resolve fmt` | Identity's question may never offer budget, leave-out or finish options | Identity | decision | C |
| `j2.py:5097-5103` | FORCED | `_identity_resolve` | With no decision-ready question, code writes one from both final positions | Identity | decision | C |
| `j2.py:5109` | FORCED | `_identity_resolve/_apply defaults` | No ruling: proposal parked, HOLD stands, finding stands (5894, 5923, 5938) | Identity | decision | C |
| `j2.py:5130` | FORCED | `_identity_question` | needs_decision, or Adaptation asking with credits < cheapest part, forces the code limit question | Identity | decision | C |
| `j2.py:5160` | FORCED | `_identity_approval` | An approved increase defaults to the shortfall and is capped by code | Identity | guardrail | C |
| `j2.py:5171-5175` | FORCED | `_identity_approval` | With no 2-option question, code writes "Approve / Don't run" | Identity | decision | C |
| `j2.py:5253` | KEYWORD | `_identity_hears_requester ONLY_PICK` | A bare option number overrides Identity's reading of the answer | Identity | guardrail | C |
| `j2.py:5262-5279` | FORCED | `_identity_hears_requester` | continue becomes drop when not offered; unclear answer re-asked once, then continue/ship default | Identity | decision | C |
| `j2.py:5298-5300` | FORCED | `_identity_hears_requester` | Dropped items are forced to equal the clicked option's items | Identity | guardrail | C |
| `j2.py:5306-5310` | HIDDEN | `_identity_hears_requester` | Code overwrites Identity's to_requester and to_agents text on a drop | Identity | guardrail | C |
| `j2.py:5320-5328` | FORCED | `_identity_hears_requester` | "Finish" on a doc in a chain accepts it and starts the next stage | Identity | decision | B |
| `j2.py:5332` | NAME | `_identity_hears_requester` | Code's finish text: "the site as it is now" vs the document wording | Identity | decision | B |
| `j2.py:5356-5360` | FORCED | `_identity_hears_requester` | After a drop, Audit must re-check before anything else | Identity, Audit | decision | C |
| `j2.py:5368-5376` | FORCED | `_identity_hears_requester` | A limit answer always routes to Adaptation and renews MAX_CYCLES | Identity | decision | C |
| `j2.py:5392-5398` | KEYWORD | `_requester_noun` | Regex replaces "site/website" with "document" in Requester text | Identity | decision | B |
| `j2.py:5407` | KEYWORD | `_fact_question NUMBER_ASK` | A doc fact question with number words gets "over what time" appended | Identity | decision | B |
| `j2.py:5468` | KEYWORD | `_gap_rows must_keep` | Core items (keyword fallback) can't be offered for leave-out (followups #13) | Identity | decision | C |
| `j2.py:5472-5484` | FORCED | `_gap_rows` | Doc gaps are grouped by workflow sections; their items leave out together | Identity | decision | B |
| `j2.py:5496-5509` | NAME | `_goal_done` | Done text picked by docset/is_page; playbook saved only on non-document runs | Identity | decision | B |
| `j2.py:5511-5590` | FORCED | `_identity_limit` | Code fixes the options; LIMIT_ADD default add; capped by BUDGET_CAP | Identity | decision | C |
| `j2.py:5531` | FORCED | `_identity_limit stale` | "Keep going" is withheld when the last continue changed nothing | Identity | decision | C |
| `j2.py:5547-5550` | FORCED | `_identity_limit` | Doc: no leave-out option if fewer than 2 sections would remain | Identity | decision | B |
| `j2.py:5559-5574` | FORCED | `_identity_limit` | "Finish" offered only when a site version exists; "stop" added for chains | Identity | decision | C |
| `j2.py:5575-5582` | KEYWORD | `_identity_limit lead` | The question's first sentence is chosen by regex/prefix on the reason string | Identity | decision | C |
| `j2.py:5594` | FORCED | `_identity_limit prompt` | Identity limited to 2 sentences; banned words "cap", "cycles", "done-when", "estimate", "building time" | Identity | decision | C |
| `j2.py:5605` | HIDDEN | `_identity_limit check_summary` | Doc: Identity's message replaced by code's check summary | Identity | decision | B |
| `j2.py:5606-5611` | KEYWORD | `_identity_limit BUILT_CLAIM` | A regex "is built/has" claim replaces Identity's message when nothing passed | Identity | guardrail | C |
| `j2.py:5619-5625` | FORCED | `_identity_limit` | A question with a single option is applied without asking (ship) | Identity, Requester | decision | C |
| `j2.py:5637-5652` | KEYWORD | `_finish_only_option must_keep` | Keyword-fallback core items named as unpayable and undroppable "core to your site" | Identity | decision | C |
| `j2.py:5670-5679` | NAME | `_open_list` | Rubric, browser check and conditions skipped for docs; RENDER_CONDITIONS skipped for pages | Identity | decision | B |
| `j2.py:5694` | FORCED | `_identity_audit workable` | Code, not Identity, decides done; Identity's done is overridden either way | Identity | guardrail | C |
| `j2.py:5702` | KEYWORD | `_identity_audit item_min` | Budget needed for left-out items read from item words (followups #1) | Identity | decision | C |
| `j2.py:5709-5719` | FORCED | `_identity_audit` | Same failure_signature twice, or only TBC left, forces the limit question | Identity | decision | C |
| `j2.py:5752` | NAME | `_identity_audit prompt` | J2.h prompt lists page checks (JS errors, overflow 360/1280, forms, links) for every type | Identity | decision | B |
| `j2.py:5761-5766` | FORCED | `_identity_audit` | Workable with only accepted items open: done without Identity declaring it | Identity | decision | C |
| `j2.py:5824-5845` | FORCED | `_can_dispute` | Adaptation may dispute only an Audit finding or a HOLD, once each | Adaptation | decision | C |
| `j2.py:5873` | FORCED | `_turn_dispute MAX_ATTEMPTS` | A disagreement escalates to Identity after 4 attempts (hard-coded) | Adaptation, Audit, Coordination | decision | C |
| `j2.py:5907` | FORCED | `_apply repriced` | A J2_FIXES ruling that costs more goes back to Priority once; that answer is final | Priority, Identity | decision | C |
| `j2.py:5942-5953` | FORCED | `_bargain_over` | Bargain ends at BARGAIN_MINUTES or BARGAIN_CALLS | Adaptation, Priority | guardrail | C |
| `j2.py:5971` | NAME | `WF_FMT` | Workflow schema says revises rewrites a "site section" | Adaptation | decision | B |
| `j2.py:5982` | FORCED | `ATOM_RULES` | Exactly one work atom "a1" per workflow | Adaptation | decision | C |
| `j2.py:6005-6012` | NAME | `ATOM_RULES` | Per-feature behaviour list: calculator, conditional field, countdown, menu active class, contrast toggle | Adaptation | decision | B |
| `j2.py:6013` | FORCED | `ATOM_RULES` | Tells the planner the builder gets 3 attempts | Adaptation | decision | C |
| `j2.py:6018-6024` | NAME | `ATOM_RULES` | Page rubric: tap 44px/24px, 9+ controls, j2-btn/j2-card, index.html, R-1..R-6 | Adaptation | decision | B |
| `j2.py:6024-6030` | KEYWORD | `ATOM_RULES` | A goal naming a time/price/number/email needs facts-present; a count with a number expects it (prompt side of #7) | Adaptation | decision | C |
| `j2.py:6057` | FORCED | `_turn_adaptation _stage_gate` | Chain funding checked once before the first plan | Adaptation | decision | C |
| `j2.py:6059-6070` | FORCED | `_turn_adaptation adapt_idle` | Adaptation isn't asked again when nothing changed; Identity asks instead | Adaptation | decision | C |
| `j2.py:6078-6086` | KEYWORD | `relevant_lessons/relevant_playbooks` | Lessons and playbooks offered by word and business_type match | Adaptation | decision | C |
| `j2.py:6247` | KEYWORD | `_turn_adaptation must_keep` | Code lists the items Adaptation may never leave out (keyword fallback, #13) | Adaptation | decision | C |
| `j2.py:6262-6265` | FORCED | `Adaptation task` | Only build workflows; an audit kind is refused | Adaptation | guardrail | C |
| `j2.py:6265-6268` | FORCED | `Adaptation task` | Each covered item costs at least its rate-card minimum; one 'fix' part per finding | Adaptation, Priority | decision | C |
| `j2.py:6269` | FORCED | `Adaptation task` | After the first Audit, every workflow must cover an item or fix a finding | Adaptation | decision | C |
| `j2.py:6270-6273` | NAME | `Adaptation task` | Each workflow's agent owns one section of the site file | Adaptation | decision | B |
| `j2.py:6278-6283` | FORCED | `Adaptation task` | Never ask about budget, cost or cutting; propose what fits | Adaptation | decision | C |
| `j2.py:6289` | NAME | `Adaptation task doc_plan_data` | Document runs get extra plan data, keyed on self.doc | Adaptation | decision | A (A6) |
| `j2.py:6305-6315` | KEYWORD | `_budget_question BUDGET_TALK` | Budget-word question rejected, re-asked once, then replaced by code's _cheapest_fit (#2) | Adaptation | decision | C |
| `j2.py:6316` | FORCED | `_usable` | An unusable reply is re-asked once, then code proposes itself (_code_fix) | Adaptation | decision | C |
| `j2.py:6342-6350` | FORCED | `_turn_adaptation` | A doc with no workflows stops the run; pages fall through | Adaptation | guardrail | B |
| `j2.py:6358` | FORCED | `_turn_adaptation _pick` | A proposal always goes to Priority | Adaptation | guardrail | C |
| `j2.py:6390-6395` | FORCED | `_turn_adaptation` | No workflows proposed: Audit re-checks before Identity | Adaptation | decision | C |
| `j2.py:6400` | NAME | `REAL_NOTE` | Unused constant naming index.html and single-page site (dead code) | none | decision | B |
| `j2.py:6407-6419` | KEYWORD | `_real_note` | Planner told time/price/number/email goals need facts-present | Adaptation | decision | C |
| `j2.py:6421-6427` | NAME | `_realization_applies` | Realization plan only for page runs, not documents | Adaptation | decision | B |
| `j2.py:6460` | FORCED | `_realization_plan` | Blocking Requester facts are asked once only | Adaptation, Identity | guardrail | C |
| `j2.py:6470-6485` | NAME | `_realization_plan text` | "Propose exactly these"; index.html; file workflows limited to 4 check types | Adaptation | decision | B |
| `j2.py:6491-6493` | NAME | `_change_applies` | J2_CHANGE only for non-document, non-blueprint runs | Identity | decision | B |
| `j2.py:6503-6511` | FORCED | `_start_work` | An unchanged diff ends the run with code's message; a goal change forces a full replan | Identity, Adaptation | decision | C |
| `j2.py:6540-6544` | FORCED | `_turn_change` | A change plan still breaking rules after one retry forces a replan | Adaptation | decision | C |
| `j2.py:6562` | FORCED | `_turn_change` | A change costing more than the credits left forces the limit question | Identity | guardrail | C |
| `j2.py:6571-6581` | KEYWORD | `_change_cost` | Revision priced as one fix; new rows priced by item_min words or page_section | Priority | decision | C |
| `j2.py:6583-6600` | NAME | `_change_rows` | Code names revisions "<name> (change k)", later read back by name (#6/#11) | Adaptation | decision | C |
| `j2.py:6602-6614` | FORCED | `_change_text` | Propose exactly these and nothing else; file workflows use 4 check types | Adaptation | decision | C |
| `j2.py:6635` | FORCED | `RELAY_ROUNDS` | 2 objection rounds before Identity rules | reader workflows, Identity | decision | C |
| `j2.py:6639-6690` | FORCED | `_change_relay/_relay_doc_revise 6719/_relay_revise 6791` | Code registers revisions without Adaptation or Priority; cost copied from the original | Adaptation, Priority | decision | C |
| `j2.py:6650-6651` | KEYWORD | `_change_relay is_artifact` | Planning docs identified by the shape of outputs strings (#12) | none | decision | C |
| `j2.py:6700-6708` | FORCED | `_relay_ask` | An unreadable reader answer after one retry counts as agreed and affected | reader workflows | decision | C |
| `j2.py:6846-6870` | FORCED | `_atoms_checked` | Atom problems get one retry, then those workflows are dropped | Adaptation | guardrail | C |
| `j2.py:6873` | FORCED | `_kind_problem` | kind must be build or audit | Adaptation | guardrail | C |
| `j2.py:6900-6915` | HIDDEN | `_carry` | Code restores the sections/kind Priority dropped or changed | Priority | guardrail | C |
| `j2.py:6953-6977` | FORCED | `_code_fix` | Code proposes revisions of escalated atoms, one fix part each, else _cheapest_fit | Adaptation | decision | C |
| `j2.py:6968` | HIDDEN | `_code_fix corrected_check` | Doc check targets rewritten by code from the document text | Adaptation, Audit | decision | B |
| `j2.py:6980-6990` | KEYWORD | `_plan_gaps` | A condition counts as planned if its "plan" regex matches the workflow JSON (#3) | Adaptation | decision | A (A9) |
| `j2.py:6989` | NAME | `_plan_gaps key` | A condition with a key waits for the earlier document's chain link | Adaptation | decision | B |
| `j2.py:7008-7013` | NAME | `_blueprint_plan` | Prompt by code: one workflow per LLD section | Adaptation | decision | B |
| `j2.py:7015-7030` | NAME | `_lld_gaps` | Every LLD section needs a workflow; styling/fix parts exempt from citing one | Adaptation | decision | B |
| `j2.py:7032-7055` | FORCED | `_plan_checked` | A plan gap gets one retry, then goes ahead with a warning | Adaptation | guardrail | C |
| `j2.py:7061-7103` | FORCED | `_doc_plan_gaps` | Doc plan: exactly one workflow per section and one per item (R1/R2) | Adaptation | decision | A (A6) |
| `j2.py:7130` | NAME | `_atom_problems` | A file workflow is limited to DOC_CHECK_TYPES + file-exists | Adaptation | decision | B |
| `j2.py:7135` | HIDDEN | `_atom_problems facts_to_headings` | Facts-present strings rewritten as headings by their shape (#8) | Adaptation, Audit | decision | C |
| `j2.py:7137-7139` | KEYWORD | `_atom_problems check_problems` | Atom checks must fit the goal by regexes (#7) | Adaptation | decision | C |
| `j2.py:7140-7146` | FORCED | `_atom_problems HEADING_CHECKS` | A doc workflow needs heading-present and section-not-empty for every section | Adaptation | decision | B |
| `j2.py:7149-7175` | HIDDEN | `_fix_atoms` | Code rewrites atoms: splits heading lists, expect-text→expect-visible, adds "create" constraints; event log only | Adaptation, Builder, Audit | decision | C |
| `j2.py:7177-7188` | FORCED | `_priority_file_note` | Tells Priority to fund file workflows with their builds and question only their cost | Priority | decision | C |
| `j2.py:7190-7193` | KEYWORD | `_file_wf is_artifact` | A file workflow is read from the shape of outputs, non-doc runs only (#12) | Adaptation | decision | C |
| `j2.py:7237-7262` | FORCED | `_cheapest_fit` | Code's own plan: one workflow per item, must_keep first, priced by item_min | Adaptation, Priority | decision | C |
| `j2.py:7257` | NAME | `_cheapest_fit PAGE_FILE` | Outputs are always the page file, even on doc runs | Adaptation | decision | B |
| `j2.py:7265-7287` | FORCED | `_left_by_ruling` | An item deferred in 2 rounds, or unpayable by item_min, forces the Requester question | Identity, Adaptation | decision | C |
| `j2.py:7328-7332` | FORCED | `_adaptation_responds task` | After REFUSE Adaptation must REVISE or PARK; "exchange n of MAX_ATTEMPTS(4), then Identity rules" written as rule | Adaptation | decision | C |
| `j2.py:7334-7344` | FORCED | `_adaptation_responds` | Coerces act: WITHDRAW→PARK, invalid ACCEPT→REVISE/PARK, empty REVISE→PARK | Adaptation | guardrail | C |
| `j2.py:7360` | FORCED | `_adaptation_responds/_bargain_over` | Escalates to Identity at MAX_ATTEMPTS exchanges or bargain cap, whatever agents want | Adaptation, Priority, Identity | decision | C |
| `j2.py:7364` | FORCED | `_pick (adaptation)` | Adaptation may hand only to Priority or Identity; other "next" redirected | Adaptation | guardrail | C |
| `j2.py:7408` | FORCED | `Priority fmt next_field` | Priority may name Identity only after MAX_ATTEMPTS exchanges | Priority | decision | C |
| `j2.py:7411-7414` | FORCED | `Priority task text` | Tells Priority to COUNTER/REFUSE plans priced below rate-card per-item minimums | Priority | decision | C |
| `j2.py:7416` | FORCED | `Priority task text` | "Prices are fixed by the rate card": Priority may cut parts, never change price | Priority | decision | C |
| `j2.py:7417-7421` | FORCED | `Priority task text (change)` | Change's planning-document revisions "come first by the change rule; never cut them" | Priority | decision | B |
| `j2.py:7424-7436` | FORCED | `_turn_priority GRANT re-ask` | GRANT without price is re-asked once (range(2)) | Priority | guardrail | C |
| `j2.py:7440-7446` | FORCED | `_turn_priority` | Bad decision, GRANT over remaining budget, or empty COUNTER become REFUSE | Priority | guardrail | C |
| `j2.py:7469` | FORCED | `_pick (priority)` | Priority may hand only to Adaptation before exchange cap | Priority | decision | C |
| `j2.py:7475-7486` | KEYWORD | `_per_item → item_min` | Rate-card minimum per done-when item read from item words (followups #1) | Priority | decision | C |
| `j2.py:7512-7519` | FORCED | `_priority_prices_ruling` | Priority prices Identity's ruling exactly once, "your answer is final"; invalid→REFUSE | Priority, Identity | decision | C |
| `j2.py:7529-7540` | FORCED | `_priority_prices_ruling` | Over-budget ruling → code-written two-option question to Requester (add credits / accept Priority) | Identity, Requester | guardrail | C |
| `j2.py:7573-7599` | FORCED | `_kept_price` | GRANT echo without price keeps code's computed price; posted as system note | Priority | guardrail | C |
| `j2.py:7604,7622` | NAME | `_agree (first = self.doc)` | Section-coverage gap re-ask only on a document stage's first plan | Adaptation | guardrail | B |
| `j2.py:7629-7636` | FORCED | `_agree handoff text` | Plan gap: code routes to Adaptation, tells it to propose workflows naming "sections" | Adaptation | guardrail | B |
| `j2.py:7642-7656` | FORCED | `_unwritten_sections` | Coverage gap asked once per stage (cover_asked), then silently dropped | Adaptation | decision | B |
| `j2.py:7659` | FORCED | `REQUIRED` | Fields name, goal_gap, outputs, completion_check required on every workflow | Adaptation | guardrail | C |
| `j2.py:7664` | KEYWORD | `_reject` | Event type role_refusal vs refused by substring "Audit's job" in reason | (metrics) | guardrail | C |
| `j2.py:7668-7679` | NAME | `_owns` | Ownership text: document names section headings, page names workflow/section id (self.doc) | all agents | guardrail | B |
| `j2.py:7689-7694` | KEYWORD | `PLAN_NAME/_plan_name` | Plan row of a fix/revision by stripping "Revise W-n ", "Fix ", " (change n)" (followups #6) | Adaptation, Validator | decision | C |
| `j2.py:7717-7733` | FORCED | `_late_judge (gate = THRESHOLD)` | Late proposals scored against code threshold; Adaptation improves exactly once | Adaptation | decision | C |
| `j2.py:7771-7776` | HIDDEN | `_late_judge` | Code overwrites completion_check and goal_gap with judge-improved versions; Priority/Adaptation not told | Adaptation, Priority, Audit | decision | C |
| `j2.py:7777-7779` | FORCED | `_late_judge` | Judge unreachable → workflow registered unjudged | Validator | guardrail | C |
| `j2.py:7795-7798` | KEYWORD | `_plan_row` | Finds realization row by name or _plan_name stripping (followups #6) | Validator | decision | C |
| `j2.py:7800-7813` | HIDDEN | `_fill_from_plan` | Fills missing fields from plan; outputs = type file/PAGE_FILE if covers else artifacts/<slug>.md; autofix log only | Adaptation, Builder | decision | B |
| `j2.py:7826-7828` | FORCED | `_register (plan_ix sort)` | Registration order and W-ids follow realization plan order, affecting which fit remaining budget | Validator, Coordination | guardrail | C |
| `j2.py:7831-7834` | FORCED | `_register` | During change "plan" phase, rejects workflows not named in change plan | Adaptation | guardrail | C |
| `j2.py:7845-7848` | NAME | `_register (self.doc sections)` | Document workflow must name template sections; page skips check | Adaptation | guardrail | A (A6) |
| `j2.py:7849-7850` | FORCED | `_register sec_min` | Multi-section document workflow must cost ≥ sum of section rate-card parts | Adaptation, Priority | decision | B |
| `j2.py:7852-7853` | FORCED | `_register` | kind=="audit" workflow rejected as "Audit's job" | Adaptation | guardrail | C |
| `j2.py:7863-7865` | FORCED | `_register` | Judge score below THRESHOLD → validator rejects | Adaptation | decision | C |
| `j2.py:7867-7870` | FORCED | `_register` | Cost ≤0 or over remaining budget rejected | Adaptation, Priority | guardrail | C |
| `j2.py:7868` | FORCED | `_register → _underpriced` | Rate-card underpricing check rejects workflow | Adaptation, Priority | decision | C |
| `j2.py:7873-7876` | KEYWORD | `_register change resend` | Refused change row resent vs cut decided by substring "left in the budget" in reason | Adaptation | decision | C |
| `j2.py:7879-7887` | FORCED | `_register envelope` | money_limit overwritten with cost; ENVELOPE_DEFAULTS (2 calls, 1 retry) fill gaps | Priority, Builder | decision | C |
| `j2.py:7896-7899` | HIDDEN | `_register` | Fix naming no sections silently inherits revised workflow's sections (doc only) | Builder, Audit | guardrail | B |
| `j2.py:7900-7902` | HIDDEN | `_register LLD` | Code appends lld-slice check ("The page matches LLD...") to first atom's verification | Builder, Audit | guardrail | B |
| `j2.py:7906-7911` | FORCED | `_register section` | revises honoured only if section exists and is not taken; else new section | Adaptation, Builder | guardrail | C |
| `j2.py:7915-7918` | KEYWORD | `_register → is_artifact` | Planning-doc revision keeps version by outputs shape (followups #12) | Validator | decision | C |
| `j2.py:7936-7949` | FORCED | `_register change` | Change rows not registered are cut and posted; change phase moved to build | Adaptation, Identity | decision | C |
| `j2.py:7952-7968` | KEYWORD | `_supersede` | Waiting workflow superseded by same name minus " (change n)", or held with same items (followups #11) | Coordination, Identity | decision | C |
| `j2.py:7970-7972` | NAME | `_lld_check_for` | Code-written check text "The page matches LLD section(s)…" | Builder, Audit | guardrail | B |
| `j2.py:8001-8004` | NAME | `_underpriced` | Parts page_section/form must list covers; after first Audit every workflow must cover or fix | Adaptation | decision | B |
| `j2.py:8006-8008` | FORCED | `_underpriced` | A fix needs one 'fix' part per finding (part name in code) | Adaptation, Priority | decision | C |
| `j2.py:8010-8014` | KEYWORD | `_underpriced → item_min/item_kind` | Minimum price per newly covered item from item words (followups #1) | Adaptation, Priority | decision | C |
| `j2.py:8033-8047` | FORCED | `_turn_coordination change resend` | Refused change rows re-asked at most 2 times, then cut | Adaptation | decision | C |
| `j2.py:8048-8053` | FORCED | `_turn_coordination` | Empty queue: code hands to Audit and refunds Coordination's turn ("Audit checks site vN") | Coordination, Audit | guardrail | C |
| `j2.py:8061-8063` | FORCED | `Coordination task text` | "One writer at a time on the site file: you hold the write lock" imposed as scheduling rule | Coordination | guardrail | B |
| `j2.py:8072-8077` | FORCED | `_turn_coordination` | Ids missing from Coordination's order appended; holds lifted by settled conflict can't be re-held | Coordination | guardrail | C |
| `j2.py:8095-8096` | FORCED | `_pick (coordination)` | With ready work Coordination must hand to Priority | Coordination | decision | C |
| `j2.py:8101-8109` | FORCED | `_turn_coordination hold_bounces` | All-HOLD goes to Adaptation once; second time code sends to Audit | Coordination, Adaptation | decision | C |
| `j2.py:8114-8135` | FORCED | `_priority_envelope` | Code checks envelope numbers and posts "allowed" as Priority without a call | Priority | guardrail | C |
| `j2.py:8143-8157` | FORCED | `_priority_envelope` | Approval may be asked once per workflow; else HOLD → status unfunded | Priority, Identity | decision | C |
| `j2.py:8181-8182` | KEYWORD | `_turn_workflow_agent → _file_wf` | File vs section build path chosen from outputs shape (followups #12) | Builder | decision | C |
| `j2.py:8185-8189` | NAME | `_turn_workflow_agent` | Artifact kind "website", section "Section", doc heading from expected_output | Builder | guardrail | B |
| `j2.py:8204-8206` | FORCED | `SITE_LIMIT` | Builder sees first 150,000 chars of site | Builder | guardrail | B |
| `j2.py:8210` | FORCED | `_turn_workflow_agent first` | First page workflow to run must write the style guide; documents have none | Builder | decision | B |
| `j2.py:8236-8243` | NAME | `style_task` | Code prompt imposes WCAG AA, 44px buttons, --j2-* vars, j2-btn/j2-card, "no other colours or fonts" | Builder | decision | B |
| `j2.py:8245` | FORCED | `limit` | Failed check buys one extra call beyond model_call_limit | Builder | guardrail | C |
| `j2.py:8291-8298` | NAME | `page builder prompt` | "site file", head/section blocks, build only covered items, rubric capped to first 6 lines | Builder | decision | B |
| `j2.py:8312` | FORCED | `builder call` | max_tokens=16000 | Builder | guardrail | C |
| `j2.py:8335-8341` | FORCED | `one_call retry` | Unusable reply retried up to envelope retry_limit, then fails | Builder | guardrail | C |
| `j2.py:8369-8373` | HIDDEN | `style section` | Code inserts style CSS as first section "Style guide" owned by first builder | Builder, Audit | guardrail | B |
| `j2.py:8376-8383` | NAME | `_turn_workflow_agent` | Title default "Site"; files site/vN.html, site/index.html vs site/vN.md + out file | Builder | guardrail | B |
| `j2.py:8377` | HIDDEN | `assemble_doc (def 2738-2747)` | Code appends "## Assumptions to confirm" from Assumption: lines; Audit sees it as builder content | Audit, Builder | decision | A (A1) |
| `j2.py:8389-8396` | FORCED | `_spec_conflict use` | Builder's spec conflict revises LLD check or stops attempts | Builder | decision | B |
| `j2.py:8402` | FORCED | `MAX_CHECK_ATTEMPTS` | Builder gets 3 check attempts | Builder | decision | C |
| `j2.py:8405-8410` | KEYWORD | `early stop → _blames_other` | Stops retries on same evidence twice or W-n + blame words in say (followups #10) | Builder, Adaptation | decision | C |
| `j2.py:8421` | FORCED | `builder next` | Builder always reports to Coordination, whatever "next" says | Builder | guardrail | C |
| `j2.py:8431-8433` | FORCED | `SITE_WARN_BYTES` | Warns over 60 KB "single-page rule" | Builder, Audit | guardrail | B |
| `j2.py:8434-8443` | FORCED | `_turn_workflow_agent` | Failed atoms routed by code to Adaptation (atom_failed) | Adaptation | guardrail | C |
| `j2.py:8468-8478` | FORCED | `_capped INPUT_LIMIT` | Inputs in builder prompt cut at 20,000 chars (announced) | Builder | guardrail | C |
| `j2.py:8490-8491` | NAME | `_artifact_context` | Tells builder to follow artifacts' "Rules for later workflows" section by name | Builder | decision | C |
| `j2.py:8506` | FORCED | `_run_artifact charter` | Code picks charter keys a file builder sees | Builder | decision | C |
| `j2.py:8515` | FORCED | `_run_artifact loop` | MAX_CHECK_ATTEMPTS and call limit bound file writes | Builder | guardrail | C |
| `j2.py:8519-8522` | FORCED | `_run_artifact task` | "Builds no part of the site"; "mark anything charter lacks as an assumption" | Builder | decision | C |
| `j2.py:8573-8584` | HIDDEN | `_human_output` | Code cuts to 3 sentences or rewrites human_output; autofix log only | Builder, Requester | guardrail | C |
| `j2.py:8586-8611` | HIDDEN | `_atom_outputs` | Cuts to 2 sentences or code-writes fallback atom_human_output; one re-ask | Builder, Requester | guardrail | C |
| `j2.py:8616-8630` | FORCED | `_agent_output` | Code builds what other agents read; section_names capped at 6 headings | Builder | guardrail | C |
| `j2.py:8631` | NAME | `_agent_output → build_agent_output(self.doc)` | Agent output shape differs doc vs page | Builder | guardrail | B |
| `j2.py:8632-8646` | FORCED | `_seal_atoms` | Passed atom becomes failed if human or agent output missing | Builder | guardrail | C |
| `j2.py:8654` | FORCED | `BOARD_FMT` | At most one board question per atom | Builder | decision | C |
| `j2.py:8663-8666` | FORCED | `FN_BOARD_FMT` | At most one board question per turn for functions | all functions | decision | C |
| `j2.py:8675` | NAME | `_dep_sections` | Skips section key "style" | Builder | guardrail | B |
| `j2.py:8715` | NAME | `_page_context` | Whole "SITE FILE" given read-only, cut at SITE_LIMIT | Builder | guardrail | B |
| `j2.py:8730-8756` | NAME | `_doc_atoms/_slice_edges/_hld_edges/_chain_edges` | Provenance edges hard-code prd/hld/lld and their section keys | (records) | guardrail | B |
| `j2.py:8814-8828` | FORCED | `_ask_board` | Refuses question: one per atom/turn, unbuilt target, self-ask | Builder, functions | decision | C |
| `j2.py:8818` | KEYWORD | `_ask_board → j2_board.duplicate_of` | Duplicate question if 60% content words match | Builder, functions | decision | C |
| `j2.py:8831-8843` | KEYWORD | `_ask_board` | to in ("requester","user","you") rerouted to Identity | Identity | guardrail | C |
| `j2.py:8856` | KEYWORD | `_ask_board` | Answer "not mine"/"n/a"/"none" → unanswered | Builder, functions | decision | C |
| `j2.py:8865-8876` | FORCED | `_ask_board doc_up` | Document change by board answer refused unless owner; PRD goes to Identity | Builder | guardrail | B |
| `j2.py:8893-8895` | FORCED | `_board_answer rules` | Answer from record only, 1-2 sentences, no counter-question | Builder, functions | guardrail | C |
| `j2.py:8906-8919` | NAME | `_board_answer` | artifact_update shape: doc section markdown vs page body/head | Builder | guardrail | B |
| `j2.py:8937-8964` | HIDDEN | `_apply_board_update` | Page section replaced by board answer, new site version, no checks rerun; doc skipped | Audit, Coordination | decision | B |
| `j2.py:9001-9003` | FORCED | `_board_doc_update` | Section must be in output_def(kind) sections | Builder | guardrail | B |
| `j2.py:9007-9019` | NAME | `_board_doc_update kind=="prd"` | PRD never changed from board; becomes Identity change request | Identity | decision | B |
| `j2.py:9040` | HIDDEN | `_revise_doc` | Code appends "Version n: Q-k, reason." into the document section text | Audit, Requester | decision | B |
| `j2.py:9054-9070` | NAME | `_write_doc` | kind- version file tag; chain ids from requirements/components; kind=="lld" resets blueprint | (records) | guardrail | B |
| `j2.py:9213-9245` | HIDDEN | `_board_forward` | Writes a passed "recheck" receipt for atoms built after a doc change | Audit | guardrail | B |
| `j2.py:9446-9459` | FORCED | `_spec_conflict` | First LLD conflict per section revised by code; second escalates | Builder, Adaptation | decision | B |
| `j2.py:9461-9512` | HIDDEN | `_revise_lld` | Code rewrites lld.md/blueprint from builder's selector/field changes, no LLD owner or Audit | Audit, LLD owner | decision | B |
| `j2.py:9514-9518` | KEYWORD | `_blames_other` | W-n plus regex (can't, unable, belongs, their...) = blames another section (followups #10) | Builder, Adaptation | decision | C |
| `j2.py:9520-9531` | NAME | `_owner_note` | Finds owner by id=/class= regex in HTML sections, skips "style" | Adaptation | guardrail | B |
| `j2.py:9533-9559` | NAME | `_doc_prompt` | Document builder rules: "## <Section>" heading, markdown never HTML, invent none, full rubric | Builder | guardrail | B |
| `j2.py:9588-9594` | NAME | `_route_template` | Page's first builder gets generic "design"/"Style guide" template | Builder | guardrail | B |
| `j2.py:9618-9624` | KEYWORD | `_template_need` | Page facts chosen by shared words with items (doc gets all) (followups #4) | Builder | decision | B |
| `j2.py:9627-9640` | NAME | `_template_need is_page` | LLD elements/form_fields added only for page | Builder | guardrail | B |
| `j2.py:9643` | KEYWORD | `_template_need label` | Strips "Write"/"Build" from workflow name for template routing | Builder | decision | C |
| `j2.py:9647` | NAME | `_template_need inputs` | Inputs hard-coded ("prd","hld","lld") | Builder | guardrail | B |
| `j2.py:9718-9721` | NAME | `_artifact_task` | Id prefixes G/R/C/S and order imposed in code prompt | Builder | guardrail | B |
| `j2.py:9766` | NAME | `_read_artifact` | Style guide validated by rules "design"/"Style guide" | Builder | guardrail | B |
| `j2.py:9771-9780` | NAME | `_read_artifact is_page` | Page takes HTML; document rendered by code | Builder | guardrail | B |
| `j2.py:9793,9800,9807` | NAME | `_artifact_docs` | Skips "assumptions" key; non-page types; "lld" falls back to blueprint | Builder | guardrail | B |
| `j2.py:10028-10037` | NAME | `_run_checks one()` | file-exists for file workflows; ids-unique scoped to owned doc sections | Builder | guardrail | B |
| `j2.py:10045-10048` | HIDDEN | `_run_checks kept` | Code adds section-not-empty checks for every owned section; builder not told beforehand | Builder, Audit | guardrail | B |
| `j2.py:10055` | FORCED | `_run_checks` | Check that can't run (pass None) never fails or escalates | Builder, Adaptation | guardrail | C |
| `j2.py:10085` | NAME | `_adaptation_atom_failed` | Cheapest fix price read from rate-card part "fix" | Adaptation | guardrail | C |
| `j2.py:10090-10129` | FORCED | `_adaptation_atom_failed corr` | Doc only: code decides check target wrong, defaults CHECK_WRONG unless build_wrong_reason | Adaptation | decision | B |
| `j2.py:10131-10140` | FORCED | `_adaptation_atom_failed` | Code overrides Adaptation's verdict to CHECK_WRONG with its own correction | Adaptation | decision | B |
| `j2.py:10143-10149` | KEYWORD | `check_problems on corrected check` | Word/regex rules validate correction; code's correction replaces Adaptation's (followups #7) | Adaptation | decision | B |
| `j2.py:10156-10170` | FORCED | `_adaptation_atom_failed` | Escalated: BUILD_WRONG+unaffordable→Identity, else Coordination/Audit | Adaptation, Identity | guardrail | C |
| `j2.py:10196-10201` | FORCED | `_audit_findings` | Missing finding or PASS without evidence → BLOCKED_BY_EVIDENCE | Audit | guardrail | C |
| `j2.py:10203-10205` | FORCED | `_audit_findings tbc` | Item with unconfirmed fact → TO_BE_CONFIRMED, overriding Audit's verdict | Audit, Identity | decision | C |
| `j2.py:10220-10238` | KEYWORD | `_finding_item.like` | Finding's item chosen by shared words, ≥0.6 threshold (followups #5) | Audit | decision | C |
| `j2.py:10257-10262` | NAME | `_turn_audit (self.doc)` | Separate doc vs site audit paths | Audit | guardrail | B |
| `j2.py:10269-10271` | FORCED | `_turn_audit all_pass` | all_pass computed by code incl. blocking conditions | Audit, Identity | guardrail | C |
| `j2.py:10277-10278` | FORCED | `_pick (audit)` | Audit may only hand to Identity | Audit | guardrail | C |
| `j2.py:10280-10282` | HIDDEN | `_turn_audit forced` | Test switch rewrites Audit's say from forced findings ("Site v") | Identity | guardrail | C |
| `j2.py:10293-10311` | FORCED | `_lld_compare/_lld_audit_text` | Unbuilt LLD sections = Priority drop, "warning only", told to Audit | Audit | decision | B |
| `j2.py:10313-10329` | NAME | `_chain_record` | Chain hard-codes prd requirements→hld components→lld sections | (records) | guardrail | B |
| `j2.py:10342-10344` | FORCED | `_audit_site SITE_LIMIT` | Audit sees first 150,000 chars of site | Audit | guardrail | B |
| `j2.py:10375-10394` | NAME | `_audit_site prompt` | Rubric ids R-1..R-7, "judge R-1 to R-5 on screenshot", "can't PASS measured", example fact | Audit | decision | B |
| `j2.py:10402-10403` | NAME | `_conditions` | Page checked on visible text and HTML; doc on text | Audit | guardrail | B |
| `j2.py:10443-10454` | NAME | `_audit_doc prompt` | Rubric id D-5 and label "Assumption:" in code; anything not in brief is invented | Audit | decision | B |
| `j2.py:10471-10485` | KEYWORD | `_flag_unpaid → item_kind` | Overrides Audit PASS to UNPAID when no workflow covered item; price by item words (followups #1) | Audit, Adaptation | decision | C |
| `j2.py:10487-10505` | FORCED | `_audit_rubric` | Missing/no-evidence → BLOCKED; code-measured problem overrides Audit PASS → NEEDS_REVISION | Audit | guardrail | B |
| `j2.py:10507-10530` | HIDDEN | `_force_fail` | Test switch turns a real verdict into NEEDS_REVISION agents treat as real | all agents | guardrail | C |
| `j2.py:10553-10557` | NAME | `_save_playbook prompt` | Playbook framed as "site for this kind of business", keyed by business_type | Adaptation | decision | B |
| `j2.py:10651` | KEYWORD | `_metrics` | refuses_converted_by_code counted by substring "Treated as REFUSE" | (report) | guardrail | C |
| `j2.py:10694` | NAME | `_export` | Export file = out file with .docx | (records) | guardrail | B |
| `j2.py:10702` | KEYWORD | `_write_summary` | Status from outcome prefixes "Done with open items"/"Done"/"Crashed" | (report) | guardrail | C |
| `j2.py:10744-10745` | NAME | `_write_summary sections` | Doc sections by md headings vs page section keys | (report) | guardrail | B |

### `j2_agent.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_agent.py:129-130` | NAME | `PERSONA, GATE` | Persona names per function, plus a second hardcoded 0.80 gate copied from j2_realization.THRESHOLD | none (view) | decision | C |
| `j2_agent.py:258-266,285-290` | KEYWORD | `TOPICS, STOP, records_only` | Word sets pick which record kinds lead a records-only answer (mock/no-model fallback) | all functions (Q&A) | decision | C |
| `j2_agent.py:297-298` | HIDDEN | `answer` | Records context silently cut to the last 60,000 chars before the function answers | all functions (Q&A) | guardrail | C |

### `j2_agent_models.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_agent_models.py:55-91` | NAME+KEYWORD | `GUIDE_MODELS, _GUIDE_WORDS, guide_model_for` | File-name words pick the guide model: product plan, architecture, design guide, copy, "streak rules" (brief-specific) | Adaptation (guides) | decision | C |
| `j2_agent_models.py:99` | NAME | `Charter.site_name` | Charter model carries a site-specific field | Identity | decision | B |

### `j2_agent_views.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_agent_views.py:33-35` | NAME | `doc_kinds` | Document types picked by form=="document" | none (view) | decision | B |
| `j2_agent_views.py:243-258` | NAME | `build_design` | Style guide read from the page form only | page builder | decision | B |
| `j2_agent_views.py:260-283` | NAME | `build_sections` | Page sections validated against page_type(); section id "style" skipped by name | page builder | decision | B |

### `j2_artifacts.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_artifacts.py:16-17` | NAME | `OPEN` | How a row opens, by form name (document/doc/page/image/data) | none (view) | decision | B |
| `j2_artifacts.py:42-49` | NAME | `page_types, is_page_node` | Page form singled out as "the site" for Map and groups | none (view) | decision | B |
| `j2_artifacts.py:86-96` | NAME | `_version` | Version-file pattern v<n>.html for page, <name>-v<n>.md otherwise | none (view) | decision | B |
| `j2_artifacts.py:136-140` | NAME | `rows` | Page types share one file, so only the chosen page type is listed | none (view) | decision | B |
| `j2_artifacts.py:362-389` | NAME | `tree` | "Full page source" row, site/index.html, version patterns by form=="page" | none (view) | decision | B |
| `j2_artifacts.py:515-521` | NAME | `groups` | Fixed groups "site" (Page sections) and "documents" | none (view) | decision | B |
| `j2_artifacts.py:587-600` | NAME | `groups` | Page node and its sections found by page form and site/index.html | none (view) | decision | B |
| `j2_artifacts.py:645-673` | NAME | `groups` | Documents group = types with form=="document"; versions by site/<name>-v<n>.md | none (view) | decision | B |

### `j2_board.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_board.py:21-26,50-66` | KEYWORD | `STOPWORDS, DUPLICATE_SHARE, duplicate_of` | Code refuses a builder's question when 60%+ of its words match an answered one | builders, functions | decision | C |

### `j2_change.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_change.py:169-191` | HIDDEN | `carry_checks` | Code drops facts-present checks and adds a heading-present check per old heading to a revision | Audit, builders | decision | B |
| `j2_change.py:174-175` | KEYWORD | `carry_checks.stale` | Substring heuristic (>=8 chars) decides that a check target came from a removed charter string | Audit | decision | C |
| `j2_change.py:220-226` | KEYWORD | `charter_diff` | Statement that only gains text counts as the same goal; any other change forces a full re-plan | Identity, Adaptation | decision | C |
| `j2_change.py:252-254` | FORCED | `THRESHOLD, PART` | Duplicate 0.80 gate; fixed map of judge checks to work-atom parts | Adaptation, judge | decision | C |
| `j2_change.py:268-285` | FORCED | `decide` | Code picks route A/B/C/D: removed=A, weakest part "size"=C, one improvement then C | Adaptation | decision | C |
| `j2_change.py:402-405` | HIDDEN | `edit` | Code rewrites delivers/informs on Adaptation's edited workflow regardless of its reply; judge sees code's version | Adaptation, judge | guardrail | C |
| `j2_change.py:432-434` | HIDDEN | `improve` | Code restores name, stage and delivers over the improved workflow Adaptation sent | Adaptation, judge | guardrail | C |
| `j2_change.py:438-450` | HIDDEN | `_split` | Split parts forced into the old stage; readers rewired to all parts | Adaptation | guardrail | C |
| `j2_change.py:470-471` | FORCED | `breakdown.check` | A split must have at least 2 parts (task text says 2 or 3) | Adaptation | decision | C |
| `j2_change.py:500-531` | FORCED | `placement_faults` | Each new stage needs its own decide workflow; every new workflow must read a planning workflow; C/D stage rules | Adaptation | decision | C |
| `j2_change.py:631-635` | FORCED | `plan_change` | Goal change, or rule/standard change with no item change, forces a full re-plan | Adaptation | decision | C |
| `j2_change.py:680` | FORCED | `plan_change` | A missing judge reply after improvement scores 0.0, so route C | Adaptation | decision | C |
| `j2_change.py:714-716` | HIDDEN | `plan_change` | An improvement that scored lower is silently reverted to the earlier version | Adaptation, judge | decision | C |
| `j2_change.py:738-749` | FORCED | `plan_change` | Workflows still below the gate and their readers are held; their items left out | Adaptation, Priority | decision | C |
| `j2_change.py:758-760` | FORCED | `plan_change` | Planning docs that informed a removed item are forced into revision on an edit | Adaptation | decision | C |

### `j2_check.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_check.py:24-30` | FORCED | `WIDTHS, TAP_MIN, TAP_DENSE, DENSE_COUNT` | Fixed widths 360/1280, tap minimum 44px (24 for 9+ siblings) | page builder, Audit | guardrail | B |
| `j2_check.py:280-291` | FORCED | `form_ok, form_problem` | Every HTML form must have a submit button and fire submit, or it fails | page builder, Audit | guardrail | B |
| `j2_check.py:294-314` | FORCED+NAME | `design_problems` | Hardcoded rubric ids R-2/R-3/R-6/R-7; Audit may not pass them; exactly one h1 | Audit | decision | B |
| `j2_check.py:370-372` | FORCED | `STEP_ARGS, MAX_STEPS, MAX_WAIT` | At most 8 behaviour steps, waits at most 3s | Audit, builders | guardrail | C |

### `j2_map.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_map.py:29-32` | NAME | `PERSONA_VERB, PERSONA_TAG, PERSONA` | PRD/HLD/LLD/Site type names mapped to persona titles | none (view) | decision | C |
| `j2_map.py:35-41` | KEYWORD | `send_word` | Regex over atom notes decides a send's word (dry run/sent/skipped/failed) | none (view) | decision | C |
| `j2_map.py:43` | NAME | `STEP_VERB` | Step kinds doc-sections/site-parts/send/decide/style named in code | none (view) | decision | B |
| `j2_map.py:96-99,286-307,389,428` | NAME | `build` | Send deed nodes by output form "send"; sends never done_unchecked; kept off the trunk | none (view) | decision | C |
| `j2_map.py:365-372` | NAME | `build` | Style guide node built from style.json and style_guide flag | none (view) | decision | B |
| `j2_map.py:593` | KEYWORD | `section label` | Strips build/fix/make/write prefixes from workflow names | none (view) | decision | C |

### `j2_realization.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_realization.py:25-26` | FORCED | `THRESHOLD, MAX_ROUNDS` | Gate 0.80 for funding; at most 3 revision rounds | Adaptation, judge, Priority | decision | C |
| `j2_realization.py:78-92,105-107` | FORCED | `certainty_zone, certainty_faults` | Code computes the zone from signals (2+ unknowns shift a zone) and faults a differing zone | Adaptation | decision | C |
| `j2_realization.py:109-114` | FORCED | `certainty_faults` | Analyze zone needs options+chosen; experiment zone needs 1 to 3 experiment workflows | Adaptation | decision | C |
| `j2_realization.py:172-174,196-215` | FORCED | `plan_faults` | R3 no two stages share thinking; brief factor must be owned; budget factors own no stage | Adaptation | decision | C |
| `j2_realization.py:244-245` | FORCED | `plan_faults` | Research workflow must have min_sources >= 3 | Adaptation | decision | C |
| `j2_realization.py:250-251` | NAME | `plan_faults` | Stage id "build" named in code: research may never sit there | Adaptation | decision | C |
| `j2_realization.py:252-263` | FORCED | `plan_faults` | R1/R2/R4: exactly one deliverer per item; each stage must own a factor or touch an item | Adaptation | decision | C |
| `j2_realization.py:281-283` | FORCED | `type_list` | Types whose form has tools are hidden unless J2_AGENT_TOOLS=1 | Adaptation | guardrail | C |
| `j2_realization.py:285` | NAME | `type_list` | Only document-form types get "needs" (hard dependencies) | Adaptation | decision | B |
| `j2_realization.py:336-370` | FORCED | `BASE, CRITICAL, BORDER, QUESTIONS, ITEM_WEIGHT, FACTOR_WEIGHT` | Code-fixed question weights and base 0.95 set every workflow score; D1 names "page element...document heading" | judge, Adaptation | decision | C |
| `j2_realization.py:483-487` | FORCED | `settle` | Check is "no" at 0.15 lost; any "no" caps the score at 0.79 | judge, Adaptation | decision | C |
| `j2_realization.py:510-524` | KEYWORD | `route, only_asks` | "ask:" note prefix routes a gap to Identity versus Priority and stops revision | judge, Identity, Priority | guardrail | C |
| `j2_realization.py:527-540` | FORCED | `holds` | Everything downstream of a not_ready or blocked workflow is held | Priority, Coordination | decision | C |
| `j2_realization.py:558-561,637-645` | NAME | `DELIVERABLES_FMT, types_text` | Prompt lists "policy, guide, plan or SOP" for recommended_practice; says new types are made as documents | Adaptation | decision | B |
| `j2_realization.py:648-651` | FORCED | `_web_note` | Without web access, Adaptation is told to plan no research workflows | Adaptation | guardrail | C |
| `j2_realization.py:705-710` | FORCED | `placement_task` | Task text requires a decide workflow per new stage and inputs_from a decide workflow | Adaptation | decision | C |
| `j2_realization.py:734` | FORCED | `breakdown_task` | Task text requires splitting into 2 or 3 workflows | Adaptation | decision | C |
| `j2_realization.py:746` | FORCED | `checklist_task` | Task text fixes 1 to 3 questions per done-when item | judge | decision | C |
| `j2_realization.py:762-767` | NAME | `match_task` | Prompt names "the same part of the page" and stage "build" | judge | decision | C |
| `j2_realization.py:813-819,830-836,995-1000` | FORCED | `Session.plan, _answers, run_decisions` | One resend on faults; the reply with fewer faults wins | Adaptation, judge | guardrail | C |
| `j2_realization.py:855-864` | FORCED | `Session.judge` | Revision judged same/worse cannot score above its previous score | judge | decision | C |
| `j2_realization.py:865-874` | FORCED | `Session.judge` | Within 0.05 of the gate the judge runs twice and the lower score counts | judge | decision | C |
| `j2_realization.py:913-917` | FORCED | `plan_goal` | Below 0.80 means not_ready and not funded | Priority | decision | C |
| `j2_realization.py:961-968` | FORCED | `decision_faults` | Decide workflow needs 2+ options, 1+ failure case, 1+ builder rule | Adaptation | decision | C |
| `j2_realization.py:1049-1056` | FORCED | `proposal_brief` | Held workflows left out of Adaptation's proposal; their items listed as left out | Adaptation, Priority | decision | C |

### `j2_replay_size.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_replay_size.py:39-40,119-150` | NAME | `replay` | Dev script hardcodes "site", lld and website ranges and a Brew Lab brief | none (dev tool) | decision | C |

### `j2_schema.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_schema.py:11-13` | NAME | `MAKE_FORMS, DO_FORMS, FINAL_FORMS` | Output forms doc/page/send named; page/doc/send count as final outputs | none (atom view) | decision | B |
| `j2_schema.py:14,61` | FORCED | `MAX_ATTEMPTS` | 3 failed attempts mark an atom abandoned in the view (j2.py uses 4 elsewhere) | none (atom view) | decision | C |
| `j2_schema.py:15-18` | NAME | `MAKE_CHECKS` | "lld-slice" check named in code | Audit | decision | C |
| `j2_schema.py:27-31` | KEYWORD+NAME | `CONTENT_EDGES` | Regexes on PRD/HLD/LLD prompt notes decide which edges carry a change to re-check | builders, Audit | decision | C |
| `j2_schema.py:106-119` | NAME | `outputs` | Form "doc" vs "page" chosen by file extension or doc flag; site/index.html default | none (atom view) | decision | B |

### `j2_send.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_send.py:18-23` | NAME | `DEEDS, TARGET_VAR` | Deed kinds, channels and labels hardcoded, not form data | Adaptation, Coordination | decision | C |
| `j2_send.py:31-33,40-46` | KEYWORD | `_SEND_EMAIL, _SEND_SLACK, detect_deeds` | Send verbs near "email"/"Slack" in the brief create send deeds | Adaptation, Identity | decision | C |
| `j2_send.py:34-35,49-51` | KEYWORD | `_UPDATES, asks_updates` | Brief words turn on milestone emails | Identity | decision | C |
| `j2_send.py:36-37,170-176` | KEYWORD | `_ADDRESS, _SLACK_TARGET, names_other` | Regex finds other recipients in the brief, only to tell the Requester | Identity | guardrail | C |
| `j2_send.py:80-84,149-167,212-222` | FORCED | `cap, allowed, send` | One configured recipient; cap of 10 live emails; Slack never live; no resend | none (send code) | guardrail | C |
| `j2_send.py:179-186` | NAME | `build` | Message body built from "## " headings: assumes a markdown document | none (send code) | guardrail | B |

### `j2_server.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_server.py:53` | NAME | `_send` | Default download name "prd.docx" | none (view) | decision | C |
| `j2_server.py:263-266` | NAME | `/site/ versions` | Version files v<n>.html or .md read from site/ | none (view) | decision | B |
| `j2_server.py:274-285` | NAME | `/site/` | RUN.doc picks "document" wording and md_html rendering vs raw HTML | none (view) | decision | B |
| `j2_server.py:360-366` | NAME | `docs_view` | Documents tab = types with form=="document" | none (view) | decision | B |

### `j2_studio.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_studio.py:20-22` | NAME | `PEOPLE, KIND_PERSON, DOC_KIND` | prd/hld/lld mapped to writer/designer/developer personas | none (view) | decision | C |
| `j2_studio.py:25-29,66-70` | KEYWORD | `DEVELOPER, DESIGNER, kind_of` | Regex over part names (form, cart, booking, hero...) assigns the persona | none (view) | decision | C |
| `j2_studio.py:35-40` | KEYWORD+NAME | `label` | Regex strips PRD/HLD/LLD prefixes and Build/Write/Make verbs from names | none (view) | decision | C |
| `j2_studio.py:55-63` | NAME | `doc_of` | Name prefix PRD/HLD/LLD picks the document, else "site" | none (view) | decision | B |
| `j2_studio.py:98` | NAME | `parts` | Section "style" skipped by name | none (view) | decision | B |
| `j2_studio.py:129-147` | KEYWORD | `stream` | Regex (GRANT/COUNTER/REFUSE, revis, fix, valid) rewrites function messages into stream lines | none (view) | decision | C |
| `j2_studio.py:204` | NAME | `deliverable_record` | form=="page" means "site" | none (view) | decision | B |

### `j2_template_lib.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_template_lib.py:930-980` | KEYWORD | `LIST_EACH, LIST_FIELDS, fact_fields` | Regex on charter facts ("each with", "form with the fields") creates template fields and enums | template generator, builders | decision | C |
| `j2_template_lib.py:932-938` | KEYWORD | `STOP, words` | Stopword list (includes "page", "section"), used by j2.py:9622 to pick a workflow's charter facts | template generator, builders | decision | C |
| `j2_template_lib.py:1021-1045,1206-1226` | FORCED | `coverage, route` | Code reuses a template without asking on fingerprint match or coverage 1.0; suggests extend/create | template generator | decision | C |
| `j2_template_lib.py:1228-1250` | FORCED | `route` | Two generator attempts, then the builder gets the generic template | template generator | guardrail | C |
| `j2_template_lib.py:1254,1273-1274,1286-1287` | FORCED | `EXTEND_MIN, _accept` | Reuse/extend below 0.5 coverage is overruled (extend becomes create) | template generator | decision | C |
| `j2_template_lib.py:1290-1296` | HIDDEN | `_accept` | Overruled extend's spec renamed "<name> 2..." by code | template generator | guardrail | C |

### `j2_types.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_types.py:19,323,327` | NAME | `DOC_NEEDED, load` | Required fields file/builder/atom_rules apply when form=="document" | Adaptation (type choice) | guardrail | B |
| `j2_types.py:26,402` | NAME | `DOCUMENT` | Section name "Document" reserved for the document-level template | none (schema) | guardrail | C |
| `j2_types.py:89-91` | NAME | `style_guide` | Style guide read from forms["page"] | page builder | decision | B |
| `j2_types.py:236-248` | KEYWORD+NAME | `named` | Trigger regexes and site_words pick document then page types (mock planner) | Adaptation (mock) | decision | B |
| `j2_types.py:251-253` | NAME | `page_type` | First page-form type is the default answer | Adaptation (mock) | decision | B |
| `j2_types.py:315-316` | NAME | `recorded` | A recorded run type is assumed form "document" | none (view) | decision | B |
| `j2_types.py:338-362` | NAME | `load` | Builder role file vs own text, file vs essentials, set by document/page | builders, Priority (min cost) | decision | B |
| `j2_types.py:357-358` | KEYWORD | `load (item_parts)` | Done-when words match cost.item_parts, first match sets the minimum priced part | Priority | decision | C |
| `j2_types.py:390-436` | FORCED+NAME | `create_problems, create` | Every new type Adaptation proposes is forced to form "document" | Adaptation | decision | B |
| `j2_types.py:470` | NAME | `promote` | Insert point found by literal record name "screenshots" | none (tooling) | guardrail | C |

### `j2_ui.html`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `j2_ui.html:1458-1495` | NAME | `DOC_KINDS, KIND_OF` | prd/hld/lld hardcoded; id prefix R/G/C/S mapped to a document | none (UI) | decision | C |
| `j2_ui.html:1802` | NAME | `OTYPES` | Filter tags prd/hld/lld/site/other | none (UI) | decision | C |
| `j2_ui.html:2362` | NAME | `tabs` | Tabs by form=="page" or type in prd/hld/lld | none (UI) | decision | B |
| `j2_ui.html:2773-2777` | NAME | `icon, tab` | Icon and tab picked by form page/doc | none (UI) | decision | B |
| `j2_ui.html:2806` | NAME | `run list` | Run icon page vs document by TYFORM | none (UI) | decision | B |
| `j2_ui.html:2937-2943` | NAME | `GTYPE, TYFORM, PAGENODE, DOCGROUPS` | "site" means the page type; groups fixed to prd/hld/lld/site | none (UI) | decision | B |
| `j2_ui.html:3145` | NAME | `order` | Document order starts prd, hld, lld | none (UI) | decision | C |
| `j2_ui.html:3203-3217,3378-3380` | NAME | `artGroupLabel, site group` | Group "site" and kind "style" special-cased | none (UI) | decision | B |
| `j2_ui.html:4723` | NAME | `icon` | Send deed icon by kind "send" | none (UI) | decision | C |

### `llm.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `llm.py:294` | FORCED | `_run_claude_cli` | CLI call retried once (tools calls never) | all agents | guardrail | C |
| `llm.py:430-457` | HIDDEN | `extract_json, close_json` | Truncated reply closed and parsed as complete; no agent told it was cut | all agents, Audit | guardrail | C |

### `mock_site.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `mock_site.py:6-87` | NAME | `build` | Mock site hardcodes CityCare Hospital, departments, 108 emergency number | none (mock) | decision | C |

### `negotiate.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `negotiate.py:125,213-219` | FORCED | `valid_split, ceo` | Split must sum to budget; CEO reserve dropped when numbers don't add up (posted) | department agents, CEO | guardrail | C |
| `negotiate.py:131,279-298` | FORCED | `agent_turn, run` | Escalation unlocks at turn 6; time box 10 turns; code picks the next speaker when none named | department agents, CEO | decision | C |
| `negotiate.py:350-370` | KEYWORD | `mock floor` | Mock agents parse $ figures from goal text | none (mock) | decision | C |

### `studio.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `studio.py:27-29` | FORCED | `MAX_TURNS, MAX_REVIEW_ROUNDS, MAX_QUESTIONS` | 24 turns; 2 review rounds then ship anyway; 2 teammate questions | Product, Design, Development | decision | C |
| `studio.py:296-318` | FORCED | `_auto_route` | Code routes spec, build, review and fix handoffs without Product | Product | decision | C |
| `studio.py:425-436` | FORCED | `product gates` | No build before user approval; delivered after approval or review limit | Product | guardrail | C |
| `studio.py:445-462,474,492` | KEYWORD+NAME | `mock product` | Mock brief hardcodes a hospital; regex on user words routes change/done | none (mock) | decision | C |
| `studio.py:527` | HIDDEN | `_design_turn` | Reviewer gets the site cut to 40,000 chars without being told | Design | guardrail | C |
| `studio.py:533-536` | HIDDEN | `_design_turn` | Unparseable review counts as approved | Design, Product | decision | C |

### `tools/check_doc_plan.py`

| Where | Kind | Symbol | What it decides | Agent affected | Keep? | Group |
|---|---|---|---|---|---|---|
| `tools/check_doc_plan.py:31-34` | NAME | `main` | Dev tool plans documents only (run.doc); charter written by code (mock_charter) | Identity, Adaptation | decision | B |

## Mock-only code (not counted)

- BUSINESS_TYPES/NEEDS/BOUTIQUE_PRODUCTS/guess_type 2015-2031, mock_charter 2033, lld_markup 2112, mock_section 2138, mock_page 2155, mock_prd_charter 2211, mock_form_charter 2245, mock_form_section 2256, mock_form_folder_charter/files 2264-2284, mock_doc_section 2286, mock_doc_atom 2311, mock_hld_section 2431, mock_lld_section 2455, doc_atom_for 2477 (mock atom via _data_type), MOCK_STYLE 2688, MOCK_REASON 3557, force_question role words 3216-3221. mock_atom 1688 is listed because _cheapest_fit uses it in live runs.
- _mock_folder 4614, intake mock 4819-4860, _identity_resolve mock (bean|farm, fund regexes) 5063-5090, _identity_approval mock regex 5153, _identity_hears_requester mock regexes 5211-5232, _turn_adaptation mock_plain/mock_real/mock 6097-6243 (phone, boutique, timings, bean|farm, ACTION_GOAL; only runs under llm.MOCK), _mock_change_plan 6615, _mock_doc_plan 6819 (sec_of), _mock_blueprint_plan 6992, _deliverables offline j2_types.named 4208-4216 (offline only).
- _adaptation_responds.mock 7312 (bean|farm, "Stories section"); _turn_priority.mock 7381 (stories/anim); _priority_prices_ruling.mock 7491; _identity_ruling_budget inline mock lambda 7542 (regex 1|add|yes|fund); _turn_coordination mock lambda 8065 (index.html); workflow-agent mock 8212; _run_artifact.mock 8508; BOARD_TOPICS 9264 + _board_reader/_mock_board_reuse 9269-9290 (MOCK only); _mock_board_ask 9292; _board_owner/_board_owner_atom 9307-9324 (callers 4826, 6105, 10365 all in mocks); DOC_ASKS 9328 + _mock_board_extra 9334; _mock_board_answer 9362; _mock_board_answer_doc 9389; _mock_board_answer_fn 9425; _mock_artifact 9894; _adaptation_atom_failed.mock 10098; _audit_site.mock 10350; _audit_doc.mock 10421 (followups mock row said 9922; now 10421); _save_playbook.mock 10549; _learn.mock 10591; _review.mock 10808.

## Notes

- `MAX_CHECK_ATTEMPTS` is marked a decision because it overrides the retry limit Priority sets for each workflow. The value stays as it is on this branch, as already agreed.
- The folder-stage rows (`_folder_stage` j2.py:4498-4603) describe the step-3 code. The step-3b plan removes them.
- Keep/agent labels and B/C groups are the reviewers' calls, and I checked the group A rows against the runs. A row marked B can still need its own data field once page and document go through the general path.

## Library cleanup (branch `library-cleanup`)

What happened to the library rows above, and to four more places the same rule covers. "Fixed" means the choice is
now read from data or made by the agent; "kept" means code still holds it, as a setting the agent is told or as a
guardrail. Line numbers in the rows above are as of the survey commit; the symbols are the way to find the code now.
Settings are in `templates/library-settings.json`; `j2_flow_test.py` tests `library_cleanup` and `folder_reuse` cover
every row.

| Item | Fixed / kept | Reason |
|---|---|---|
| `decision_group` (documents / pages branch) | Fixed: data | The group is the type's `group`, else its `form`, read from its entry in `artifacts/types.json` (`type_data`). Every entry has one, records included. A type only a run recorded is read from that run's `artifacts.json`. |
| `_same_business` (last word of the business type) | Fixed: charter field | Two business types are the same only when both charters recorded the same `business_type`, compared whole. No word of it is read alone. Values that record none are listed in settings (`no_business_type`). |
| `RTSCOPES` in the Library tab | Fixed: data | The server sends `scopes` (`decision_scopes`): one per group the run's decisions fall in, labelled from the type data. The page holds no type or form name. |
| Run templates of folder outputs (`run_template_from_run`, `save_run_template`) | Fixed: data | A type whose data has a `folder` is a folder of files. The run template keeps the folder's file names and its test in `outputs`; `folder_decision` records a second run's reuse. |
| `LIST_EACH`, `LIST_FIELDS`, `fact_fields` | Fixed: data | The two fact shapes, the names they make and their descriptions are entries of `fact_fields` in settings. Code loops over them. They are still patterns, now data. Without them the need names no field before the generator runs, which changes what `j2.py` hands the builders, so that step is the owner's. |
| `STOP`, `words` | Fixed: data | The word list and the least word length are in settings (`stop_words`, `min_word_length`). `j2.py` still picks a workflow's charter facts by shared words through `words()`: left for Disha. |
| `coverage`, `route`: reuse without asking | Kept: setting, agent told | `routing.reuse_without_asking` (the same need, or coverage 1.0). An identical need then costs no model call. The generator's prompt states the rule; turning both off sends every reuse to the generator. |
| `route`: two generator attempts, then the generic template | Kept: guardrail | It bounds the cost of a bad reply. The number is `routing.generator_attempts`, and the prompt states it. |
| `EXTEND_MIN`, `_accept` overruling an extend into a create | Fixed: agent decides | The number stays (`routing.extend_min`, `routing.reuse_min`) and is in the generator's prompt. A reply under it is refused with the rule and the generator is asked again; code no longer changes the action. The decision keeps the refusal (`refused`). |
| `_accept`: silent `<name> 2` rename | Fixed: removed | Code never renames. A create under a taken name is refused with the reason, and the generator picks the name. |
| `j2_agent_views.doc_kinds` (`form == "document"`) | Fixed: data | Types are picked by their template: one that names its sections (more than one section template, or a whole-artifact template) is built section by section. |
| `j2_agent_views.build_design` (page form only) | Fixed: data | Every style guide any form names is built (`style_guides`, from `j2_types.templated`). |
| `j2_agent_views.build_sections` (`page_type()`, `"style"` by name) | Fixed: data | Every type whose template has one repeating section template is built; its file path comes from the type data; an entry of `sections.json` that is no workflow of the run is skipped. |

Left as it is, and why:

- `AUTO_MIN`, `AUTO_WEIGHTS`, `VAGUE_TYPES` (`run_template_match`): numbers and a word list in code. Not in this PR's list; they move to settings the same way.
- `run_slots`, `_noun` (slot names such as `<studio name>` from the last word of the business type and from address, time and phone patterns): still used when a run template is built. Branch `sutra-library` shows templates with slots named from charter fields (`charter_slots`) instead.
- `build_design` still looks for `style.json`, the file name `j2.py` writes.
- The Library tab still skips the row focus for `d.artifact !== "design"` (one comparison in `renderLibrary`).
