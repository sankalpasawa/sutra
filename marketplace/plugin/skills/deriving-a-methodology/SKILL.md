---
name: deriving-a-methodology
version: 1.0.0
description: >
  Use when a HOW card from core:finding-the-how ends in a gap: the how for a
  piece of Native work is not known and was not found, and the next question is
  "what method would produce the how": "how do we even approach this", "what's
  the methodology", "how would we work out how", a step that keeps decomposing
  without reaching an atom, or a flow step at Mode 3 (how-of-how). NOT the
  first thing to reach for: core:finding-the-how runs first. NOT for testing a
  claim (core:native-method). The second rung of the how ladder;
  core:synthesizing-a-methodology is the third.
---

# Deriving a methodology

**status**: v1, 2026-09-25 · **owner**: Native Builder · **persona**: the Methodologist · **rung**: 2 of 3

A method is a workflow whose output is a how. When the how is unknown, the Methodologist does not guess at one; it runs a method that produces one, inside a budget, and then writes the produced how down so nobody climbs this rung for the same problem again.

This is Mode 3 of `core:flow` (run a workflow that designs the workflow, then run its output) and M3 on the Reflection ladder. Both are ruled on `holding/website/native/platform/model/workflow-engine.html`, section "Recursion". The ladder itself is in `core:finding-the-how`.

## The rule

Climb once, then amortize. The climb costs a budget; the amortization is what pays it back: the produced how becomes a workflow type, so the next instance stops at rung 1. A climb whose output is not written back was a guess with extra steps.

## The steps

| # | Step | Ends when |
|---|---|---|
| 1 | **Read the gap.** Take the HOW card. Restate what kind of how is missing in field-neutral words: the unit, what composes, what is recorded, what varies, what constrains | one line a stranger could test, and the KIND line of the card is filled |
| 2 | **Look for a method that yields hows of this kind.** Native's own first, then the M3 column below | METHOD names one, with where it lives, or reads "none known" |
| 3 | **Set the budget.** Steps, time, tokens the climb may spend, per the per-task budget rule (sheet A10, `holding/plans/native-sop-program/DESIGN-DECISION-SHEET.md`) | BUDGET is a number, not "reasonable" |
| 4 | **Run the method as a workflow.** Its output is a HOW card that passes rung 1's three-line test: steps named, each with a check that could fail, and a pointer | the HOW card exists, or the budget is spent and the card says so |
| 5 | **Amortize.** Write the produced how as a workflow type, in child scope (a company playbook or `.claude/skills/`) unless it is fleet-general, then propose it to the platform. Add the ledger row | a path exists that `core:finding-the-how` will hit in place 1 or 2 next time |
| 6 | **Hand down.** Run the how under `core:flow` | the unit proceeds at mode 1 or 2 |

Step 2 finding nothing ends this rung on a GAP line. That is the only way into rung 3.

## Native's own methods, by what the how must produce

Look here before the general column. Each one is already ruled and already has a check.

| The how must produce | The method | Where |
|---|---|---|
| an answer (T2) | the Lab card: a claim, rivals, the lowest test that could fail, a kill line before the run | `core:native-method` |
| a design of a work system | the eight-step convergent procedure: value, variety, contracted units, named patterns, soundness before run, cadence and WIP, run and conform, loop | `holding/research/2026-06-12-unit-work-record-science.md`, section 3 |
| a new thing placed in the system | the universal step, place(input, system): distill, classify, fit-test, assimilate or accommodate or reject, cascade | `holding/website/native/bootstrap.html` |
| a decision | anchor, on-path, level, real, weigh, record | `holding/website/native/platform/how-methodology.html`, §3.5 |
| a cut of a problem into steps | the inner engine: axes minted and picked, then the certainty posture | `core:lens`, `core:cynefin` |
| a workflow mined from what already ran | process discovery over the record, then conformance | the science note above, section 2 |
| a shape for a system that must change under traffic | the migration plan | `core:incremental-architect` |

## The general M3 column

When no Native method fits, the archived Method §3 page lists methods by realization tier (example 5a on `holding/website/native/platform/how-methodology.html`). Pick by the tier the how sits at. A method from this column is a technique, not yet a Native method; step 5 is what makes it one.

| Tier of the how | Methods |
|---|---|
| strategy | Wardley map, Theory of Constraints, Lean Startup |
| architecture | C4, ADR pattern, arc42 |
| feature | story mapping, Jobs-to-be-Done, Kano |
| implementation | TDD, BDD, DDD |

## The card

```
METHOD card
GAP:       <the HOW card's PROBLEM line>
KIND:      the how must produce: an answer | a workflow | a design | a decision | a structure | a cut
METHOD:    <name> (<where it lives>)  |  none known
BUDGET:    <steps> steps, <time>, <tokens>  (A10)
OUTPUT:    HOW card produced: yes, steps <n>, check <the check>  |  no: budget spent, <what was learned>
AMORTIZE:  written as <workflow type> at <path>  |  not reusable because <why>
NEXT:      run the how under core:flow  |  GAP → core:synthesizing-a-methodology
```

The card leads the reply. Inside a native-builder unit it sits under the Design phase, before the table of what changes.

## Halting

Mode 3 stacking on Mode 3 stops by reflexivity (the halting rule in `core:flow`). If the method itself needs a method, that is rung 3, not another Mode 3. If the budget is spent and no HOW card exists, the rung ends on GAP with what was learned, never on a how assembled to look finished.

## Pressure, and what the Methodologist does with it

| Pressure | What the Methodologist does |
|---|---|
| "skip the method, sketch the design" | A design with no method behind it has no check. Writes KIND and looks; a Native method usually exists |
| "we spent two days already" | The two days are the budget spent on guessing. Sets a budget for the climb and holds to it |
| the method is found but nobody has time to write it back | Step 5 is part of the unit, not a follow-up. Without it the climb repeats next session |

## Skills this rung hands to

Invoked in the session, per native-builder's routing note; not called from this file.

| When | Skill |
|---|---|
| the method is the Lab card | `core:native-method` |
| the method cuts the problem | `core:lens`, `core:cynefin` |
| the produced how runs | `core:flow`, `core:blueprint` |
| the produced how becomes a type | `core:workflow-type-resolve`, its reuse-tag route |
| GAP | `core:synthesizing-a-methodology` |

---
provenance: {author: claude, date: 2026-09-25, inputs: [the founder's direction that an unknown how is reached through its methodology, three baseline subagent runs on 2026-09-25 without this skill (two of three, told no method was known, improvised a design from "instincts" within the same reply; none named a method whose output would be a how, none set a budget, none planned to write the result back), the Recursion section of workflow-engine.html, the archived Method §3 page, the 2026-06-12 science note], with-skill run on 2026-09-25: one of one, on the hand-off scenario, named the eight-step procedure bounded by the interaction-unsafe law, set a budget of 6 steps, 90 minutes and 12k tokens, refused to sketch the design ahead of the method, and named the write-back type, review: none by a second model, confidence: high on the steps and the Native methods table, which point at ruled homes; moderate on the general column, which is the archived page's list, not a ruling}
