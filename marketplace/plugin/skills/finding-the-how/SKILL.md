---
name: finding-the-how
version: 1.0.0
description: >
  Use when a piece of Native work reaches a step and the next question is
  "how do we do this": a capability, a proof, a design, a step whose method is
  not obvious, or when someone says "nobody here has done this", "no idea how",
  "figure it out", "I have instincts but no method". Also the first move of
  native-builder's Understand and Design phases whenever the how is not already
  written. NOT for deciding whether the thing should exist (core:architect) and
  NOT for testing whether an idea works (core:native-method). The first rung of
  the how ladder; core:deriving-a-methodology is the second.
---

# Finding the how

**status**: v1, 2026-09-25 · **owner**: Native Builder · **persona**: the Scout · **rung**: 1 of 3

Nobody invents a how before looking for one. The Scout looks in four places, in order, and only then says "found" or "gap". Without this rung the same how gets invented on every session, each time without a check.

## The ladder this rung belongs to

| Rung | Question | Skill | In canon |
|---|---|---|---|
| 1 | Is there a how? | `core:finding-the-how` | M1 on the Reflection ladder; Mode 1 and 2 of `core:flow` |
| 2 | Is there a method that yields the how? | `core:deriving-a-methodology` | M3, Mode 3 (how-of-how) |
| 3 | Which fields of science hold the method? | `core:synthesizing-a-methodology` | M4 to M6, halts by reflexivity |

The Reflection ladder and the three modes are ruled on `holding/website/native/platform/model/workflow-engine.html`, section "Recursion". One rung per unit; a rung ends on its card; the next rung is entered only from a GAP line. Whatever a rung produces is written back, so the next instance stops one rung lower.

## What counts as a how

A how is known when all three hold. "Instincts", "general patterns" and "I would probably" fail the first line.

1. Its steps are named, in order.
2. Each step ends on a check that could fail.
3. It has run somewhere the Scout can point at: a workflow type, a skill, a page, a record, or a named result. A how the operator does by hand today counts; the record of it is the pointer.

## The four places, in order

Child custody wins over platform (ADR-026, `sutra/os/decisions/ADR-026-workflow-type-guidance-first-resolution.md`). Stop at the first real match; write down what was looked at either way.

| # | Place | Where to look | What a match looks like |
|---|---|---|---|
| 1 | The company's own | `.claude/skills/`, `holding/skills/`, `holding/playbooks/`, the program folder under `holding/plans/`, the style map in `holding/plans/native-sop-program/PROBLEM-STYLES.md` | a playbook or workflow type whose purpose is this work |
| 2 | The platform | the `core:*` catalog; floor: `bin/workflow-type-match.sh <intent>` from the plugin root | a skill whose description fits the purpose, not the keywords |
| 3 | The page that owns the subject | `holding/website/native/manifest.json` names it; the page says built, designed or proposed | built or designed: a how. Proposed: a hypothesis, which is `core:native-method`'s work |
| 4 | The record and the science | a past run in `.sutra/atom-ledger.jsonl` or the routine run rows; a named result in `holding/research/2026-06-12-unit-work-record-science.md`, section 6, the Rosetta table | a run that did this, or a field that has a word and a theorem for it |

A match found in place 3 or 4 but absent from places 1 and 2 is written as a workflow type before the unit closes, so the next Scout finds it in place 1.

## What is missing decides where to look

Name the problem type before looking (ADR-030, `sutra/os/decisions/ADR-030-four-problem-types.md`). The type says which kind of how can exist.

| Type | Gloss | What is missing | Where a how can be |
|---|---|---|---|
| T1 | we know it, we do it by hand | operationalisation | places 1 to 4; the how exists, find it |
| T2 | we know what we don't know | the answer | the how is an experiment: `core:native-method`'s Lab card is the known how |
| T3 | we have it, we haven't worked it out | the workflow | the record, place 4: surface the pattern, then propose |
| T4 | we don't know what we don't know | the question | no how can be found for a question nobody has asked; sense on a cadence, do not build |

## The card

```
HOW card
PROBLEM:  <one sentence, in the model's words, that a stranger could test>
MISSING:  T1 operationalisation | T2 the answer | T3 the workflow | T4 the question
LOOKED:   child: <what> | platform: <what> | page: <which> | record/science: <what>
FOUND:    <name> (<where>) → FOLLOW, mode 1 atom | mode 2 sub-workflow  |  none
CHECK:    <the check the how ends on, that could fail>
NEXT:     run it under core:flow  |  GAP → core:deriving-a-methodology
```

The card leads the reply. A FOUND line carries its CHECK into the unit's blueprint as a verify. A GAP line is the only way into rung 2.

## Pressure, and what the Scout does with it

| Pressure | What the Scout does |
|---|---|
| "nobody here has done this" | Someone has, in a field or in the record. Looks in place 4 before agreeing |
| "just build something, we're late" | Twenty minutes looking is cheaper than a day inventing; an invented how has no check, so it cannot be proved |
| "I know how" | Asks for the steps and the check. Without both, writes MISSING and looks |
| a how found with no check | Not found. Writes the steps and adds the check, or writes GAP |

## Skills this rung hands to

Invoked in the session, per native-builder's routing note; not called from this file.

| When | Skill |
|---|---|
| FOUND, and the unit runs | `core:flow`, mode 1 or 2; `core:blueprint` for the per-step checks |
| MISSING is T2 | `core:native-method` |
| GAP | `core:deriving-a-methodology` |
| the found how must be written as a type | `core:workflow-type-resolve`, its reuse-tag route |

---
provenance: {author: claude, date: 2026-09-25, inputs: [the founder's direction that the builder first finds the how, then the method, then the fields, three baseline subagent runs on 2026-09-25 without this skill (all three admitted the how was unknown and then invented one on the spot; none looked in a catalog, a page or the record first; none wrote a check it could fail), ADR-026, ADR-030, the Recursion section of workflow-engine.html, the archived Method §3 page], with-skill run on 2026-09-25: one of one, on the drift scenario, filled the card, found conformance checking in place 4 with the α-algorithm behind it, carried a fitness-score check into NEXT and planned the write-back as a type, review: none by a second model, confidence: high on the four places, which are the homes native-builder already names; the T-type row for where a how can be is the author's reading of ADR-030 Decision 1}
