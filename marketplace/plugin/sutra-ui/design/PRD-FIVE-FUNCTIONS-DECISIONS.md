# PRD build decisions: the defaults taken without the owner

| Field | Value |
|---|---|
| **status** | v1, 2026-10-23; the decision log for building [PRD-FIVE-FUNCTIONS.md](PRD-FIVE-FUNCTIONS.md) |
| Rule | the owner asked for the build to run without stopping for marks (2026-10-23: "the adaptation here is the logic where you don't need my input"). Each mark (MK) and question (Q) below takes the PRD's own proposal or default. The owner can change any row; a change reopens only the steps that row names |
| Shared page | https://claude.ai/artifact/3qnU9D85uAKd3uHVQDwxSV |

## Corrections to the PRD found before the build

| Id | Correction | Why |
|---|---|---|
| C1 | M3.1 writes the registry charter mirror through the proposals path (`proposals.create` then `proposals.decide(..., apply_fn=org2_apply.apply_request)`, as `founding._apply` does), not by writing the registry file directly | every registry write today goes through a filed, applied proposal (`founding.py` `_apply`), and README.md says the panel is read-only against the registry except through that path |
| C2 | Steps that need live model runs (M6.1 spike runs, M10.4 proof runs on Beta, Human Simulation walks) are done with stubbed models and fixtures; the live runs are listed as pending in the build report | live runs spend the owner's subscription and need Sutra Beta installed |
| C3 | Line numbers in the PRD cite sutra 6bb38ec6; after each merge, locate code by function name | the code moves as milestones land |

## Marks and questions: what was taken

| Id | The question | Taken | Steps it opens |
|---|---|---|---|
| MK-1 | J2.a: what is Identity's standard (the content of completeness.md), and what are its journeys? | five points. The goal names what and for whom; done-when has items, each with how it is checked; every rule is tagged; owner and budget are set; nothing is invented (facts not given are marked to confirm). | M3.3 |
| MK-2 | S-30 marks owed: the four goal levels, the five website angles, the version 1 way, and the three components. | each done-when item has a level (target or outcome) and a 'how'; a reading row has subject, claim, evidence, method, verdict and severity. A verification engine held by Root stays designed. | M3.2, M8.3 |
| MK-3 | J2.b with no template: which practices in place are read, are the Make module's levels in version 1, and what confidence rule leads to asking the person? (The function page's version 1 says no Make module, while J2.b says this is the focus.) | Take the M6.1 desk spike proposal, [design/PRD-FIVE-FUNCTIONS-J2B.md](PRD-FIVE-FUNCTIONS-J2B.md), as marked. Its three runs are j2-20261013-165916, j2-20261014-111512 and j2-20261016-160511 in J2_Prototype/runs. | M6.3, M6.4 |
| MK-4 | Root's version 1 standards list (J2.4 is a placeholder). | the eight standards in M7.2. | M7.2 |
| MK-5 | Screens for Adaptation, Priority, Coordination and Audit. The site says 'needs to be filled; no screen of its own yet'. | their panes S7, S8, S9 and S12. | S7, S8, S9 and S12 in stable (M4.7, M5.6, M8.8) |
| MK-6 | Internal messages: which function owns it, and is it its own row (screen 3) or a switch in Chat (the cleanup design)? | its own row, read only. | M10.1 |
| MK-7 | Each function's goal, done, settings and .md content (placeholders 'the founder's to fill'). | today's prompts, byte for byte. | Owner-written instruction content beyond the defaults (M2.2) |
| MK-8 | New structure that reopens the 2026-09-29 rulings: the All five overview (S2), state dots on function rows (S3), the progress line in the strip (S4), renaming the first tab 'About', and the prototype's richer Map boxes (this reopens the closed Map). | Build as the PRD specifies. | M1.6, M1.8, the Map extras in M1.5, and the five-function rows of S17 |
| MK-9 | Directions D-b, D-d and D-e ('not on the to-build list until you mark them'), in particular D-e: Adaptation fits the template's engines before the first run. | Build as the PRD specifies. | M5.2 |
| MK-10 | Pursue: its name and how the gap is measured (FA2, R1 placeholders). | 'next round' on screen, and the gap is the done-when items not met. | M9 in stable |
| Q1 | Voice: does only Identity speak to you (J2, S-29), or do you chat with all five (AMEND-2026-09-21-01)? | Identity only; a function's chat box sends your words to Identity about that function. | M3.6 |
| Q2 | Function-page version 1 (2026-09-30) against the J2 flow (2026-10-01): which governs each function's first release? | J2 governs, as the later and ruled word (S-29); steps beyond a page's version 1 stay in Beta until you review them. | M5, M8, M9 in stable |
| Q3 | Audit is ruled sporadic and unannounced (2026-09-27). Is J2's done-reading of every deliverable an accepted exception, and what is the spot-check cadence? | yes; once a day at a random minute. | M8.2, M8.7 |
| Q4 | Done is a code check in Identity's covering (S-23), and Audit's mechanical step is code. When a measured failure and the AI judge disagree, does the measured failure win (set against S-09 and S-22)? | yes, and both rows are kept. | M8.3, M8.4 |
| Q5 | S-25: is registering the plan on dept.workflows enough, while born engine templates stay in the app's records-home Library, tagged made_by (S-12)? | yes; per-department definitions are a later refactor. | M7 |
| Q6 | Pursue limits: the round ceiling (default 6), what happens at the limit (three priced options, capped at twice the budget), and whether 'done with open items' is an allowed end. | no 'done with open items'. | M9.2, M9.5 |
| Q7 | Goal change (J2.8): through Root again, or Identity takes your words? | Identity, as a goal rule you stamp (J4), which reopens a cycle. | M9.8 |
| Q8 | Tasks after done: keep J3 4a (your task is filed in the Brief and the registered line runs it), or always go through a new round with Adaptation and Priority? | keep J3 4a. | M9.8 |
| Q9 | The order in which the five wake (the motor table against life cycle s10). | no 'asleep' state on screen. | Any 'asleep' state |
| Q10 | Theme (warm-light only, or both) and the five function colours. | both themes, with the colours in this document. | M1.3 final values |
| Q11 | Plan size: '2 to 5, there is no limit' against the code's cap of 6. | no hard cap from Root; Priority's room bounds it. | M7.2 |
| Q12 | Which website engines are required (S-21, B3)? | only Check, because it enforces your rules (J4). | M4.4 |
| Q13 | May a counter leave out an engine without your stamp (S-06 against S-18)? | yes (S-18); the plan message names what was left out. | M4.2 |
| Q14 | Does 'ask before the first publish' count as a person having spoken (S-18; FI3, R2)? | keep it as built, as the one default ask. | None in this PRD |
| Q15 | Targets for owner effort (SM-8) and cost (SM-9). | set from the M0 baseline. | M10.4 pass or fail |
| Q16 | Step pill names (Enough to work, Propose, Price, Settle, Root's review, Run, Read, Next or done), and whether names such as 'Round 2', 'D2' and 'v3' are allowed at rest under A28. | yes; they are names, not counts. | S4 |

provenance: {author: claude, date: 2026-10-23, inputs: [PRD-FIVE-FUNCTIONS.md open questions], review: none by the owner yet, confidence: high that each row matches the PRD's stated default}
