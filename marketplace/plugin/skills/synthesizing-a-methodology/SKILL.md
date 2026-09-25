---
name: synthesizing-a-methodology
version: 1.0.0
description: >
  Use when no method is known for producing the how a piece of Native work
  needs, after core:finding-the-how and core:deriving-a-methodology both ended
  on a gap: "no one has a method for this", "we'd be inventing", "is there a
  science for this", "what field does this belong to", "from first principles",
  or a request to build a methodology from other fields of science. NOT for a
  problem whose method already exists in Native (that is rung 2) and NOT a
  licence to skip the two lower rungs. The third and last rung of the how
  ladder.
---

# Synthesizing a methodology

**status**: v1, 2026-09-25 · **owner**: Native Builder · **persona**: the Scholar · **rung**: 3 of 3

Nothing is invented that a field already proved. When Native has no method for a kind of how, the Scholar scans the fields that have studied that kind of problem, takes their named results, and assembles a method whose every step rests on one. The founding move of Native's own methodology was this question, asked on 2026-05-28: are there techniques already existing in other fields of science, rather than us discovering on our own. The answer on 2026-06-12 was that five fields had independently derived Native's structure. Convergence across fields is the signature of a science; that is the test this rung applies.

This is M4 to M6 on the Reflection ladder (`holding/website/native/platform/how-methodology.html`, §3.2), and it halts by reflexivity. The ladder itself is in `core:finding-the-how`.

## The steps

| # | Step | Ends when |
|---|---|---|
| 1 | **State the problem in field-neutral words.** The unit, what composes, what is recorded, what varies, what constrains, what regulates. These six words are the invariant triple and its neighbours, the vocabulary every field below already shares | a stranger from any of the fields would recognise the problem |
| 2 | **Scan the fields.** The table below. At least three fields; at least one named formal result with author and year | the FIELD SCAN table is filled, one row per field |
| 3 | **Test for convergence.** Two or more fields independently deriving the same move is science-grade. One field is a technique. None is a guess, and the card says so | CONVERGENCE names the rung on `core:native-method`'s evidence ladder |
| 4 | **Assemble the method as a workflow.** Each step rests on one named result and ends on a check that could fail. Write the Rosetta row so Native's word for each part maps to each field's word: the vocabulary stays closed | the METHOD line reads as steps with results, not as prose |
| 5 | **Place it.** A method is a class-B input to the bootstrap (`holding/website/native/bootstrap.html`, section 4). Assimilate when it fits an existing home: a references file under the skill that will use it, or a dated note under `holding/research/`. Accommodate when it needs a new altitude, which is core-author-gated: the founder stamps it before it is canon | PLACED names a path, or names the stamp it waits for |
| 6 | **Hand down.** The method is now known. Run it through `core:deriving-a-methodology` to produce the HOW card, then run the how | the unit proceeds at rung 2 |

## The fields, in the order to scan

Start with the five that already converged on Native's structure and the six the 2026-06-12 critic listed as unread. Reach past them only when the problem is outside unit, work and record, and then name the field and why it is the right one.

| Field | Source of record | Has a named result for |
|---|---|---|
| process science | van der Aalst | discovery from a log, soundness before run, conformance of runs to a model |
| transaction processing | Gray and Reuter | the unit contract, replay from a log, sagas and compensation |
| event sourcing and domain design | Vernon, Evans | state as a fold over events, aggregates, one writer per unit |
| operations science | Toyota, Goldratt, Hopp and Spearman | takt, WIP caps, the bottleneck law, queue time under variance (Kingman), Little's law |
| cybernetics | Ashby, Beer | requisite variety, the good regulator, the recursive system |
| coordination theory | Malone and Crowston | dependencies between activities and the mechanisms that manage them |
| organization design | Thompson, Galbraith | how human units compose: pooled, sequential, reciprocal |
| accounting, REA | McCarthy | records that constitute, reconcile and audit a system |
| scheduling theory | Kelley and Walker, PERT | precedence-constrained units over time and resources |
| system dynamics | Forrester | stocks, flows and feedback of composed work systems |
| language-action | Winograd and Flores | commitments as units; the critique of over-formalized workflow |

The formal results, fifteen of them with years, are in `holding/research/2026-06-12-unit-work-record-science.md`, section 5, and the Rosetta between Native and the first five fields is section 6. Cite rows there; do not copy them.

## The card

```
SYNTHESIS card
PROBLEM:     <field-neutral statement: unit, composition, record, variation, constraint, regulator>
FIELD SCAN:  | field | what it calls this | named result (author, year) | what it says to do | where it breaks |
             <one row per field, three or more>
CONVERGENCE: science: <fields> agree on <move>  |  technique: <one field>  |  guess: none found
METHOD:      <name>: step 1 (<result>, check: <what fails>) → step 2 (...) → ...
ROSETTA:     <Native word> = <field A's word> = <field B's word>
PLACED:      assimilated at <path>  |  accommodate: new altitude, founder stamp needed
NEXT:        run via core:deriving-a-methodology  |  escalate: <why the fields cannot decide>
```

The card leads the reply, with the scan table inside it.

## Halting

The rung that describes itself is the top (the halting rule in `core:flow`). Stop and escalate to the founder, with the scan table, when any of these holds:

- the fields disagree and no named result decides between them;
- the method needed is a method for making methods;
- no field has a word for the problem after the eleven above and one deliberate reach past them.

An escalation with a scan table is a finished rung. A method assembled to avoid escalating is not.

## Pressure, and what the Scholar does with it

| Pressure | What the Scholar does |
|---|---|
| "no time to read papers" | The scan is a table of names the Scholar already knows; twenty minutes. An invented method costs a week and has no check |
| "our problem is unique" | States the unit, the composition and the record. It is then one of the eleven |
| "just give me a formula" | Gives it, with the field and the result it comes from, and the check that shows it is wrong |
| one field found, called science | One field is a technique. The card says technique, and the placement waits for a second field or a run |

## Skills this rung hands to

Invoked in the session, per native-builder's routing note; not called from this file.

| When | Skill |
|---|---|
| the method is assembled | `core:deriving-a-methodology`, to produce the how |
| the method claims something testable | `core:native-method` |
| the placement is a new altitude | `core:writing-adr` for the decision; `core:updating-canon` for where it lands |
| the fields cannot decide | `core:codex-sutra` or `core:deepseek` in Challenge mode, then the founder |

---
provenance: {author: claude, date: 2026-09-25, inputs: [the founder's direction that a missing methodology is built from fields of science, three baseline subagent runs on 2026-09-25 without this skill (two of three never reached into a field where a mature one exists: conformance checking for drift, sagas and accordance for hand-offs; the third named Kingman and Goldratt only when the prompt asked it to, and placed the result nowhere), founder prompt 6 in §3.A of the archived Method §3 page, the 2026-06-12 science note and its critic's gap list, the bootstrap's four input classes], with-skill run on 2026-09-25: one of one, on the queue-slack scenario, scanned five fields, called the convergence science-grade on operations science and scheduling theory agreeing, tied each of five steps to a named result with a check, wrote the Rosetta row, and placed the method as a dated extension of the science note, review: none by a second model, confidence: high on the field table, which is the science note's own list; moderate on the placement step, which reads the bootstrap page's class-B rule onto methods}
