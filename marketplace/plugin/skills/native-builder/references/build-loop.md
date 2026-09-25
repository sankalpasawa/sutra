# The build loop

**status**: v1, 2026-09-23 · **owner**: Native Builder · **read when**: you are building a piece of Native and want the order, with the check that ends each phase.

Seven phases. Each one ends on a check a machine can run, not on a feeling. A phase whose check cannot run is not finished, however good the work looks.

| # | Phase | What happens | The check that ends it |
|---|---|---|---|
| 1 | **Understand** | say what must be true when this is done, in the model's own words, in one sentence | the sentence names only words the model has, and a person who was not here could tell whether it is true |
| 2 | **Place** | decide which of the ten skill sets this is, and where the work lands: registry, app store, site or plans | the path exists, or its parent does, and the set's own check is written down as this unit's verify |
| 3 | **Design** | the smallest shape that satisfies it, and what it would break. If the how is not already written, the ladder in the skill's section 4b runs first: `core:finding-the-how`, then `core:deriving-a-methodology`, then `core:synthesizing-a-methodology`, one rung at a time | a table of what changes, and one line naming what this design makes harder; when the ladder ran, its last card sits above the table |
| 4 | **Build** | write it, one file per step where the steps are separable | each file exists and the thing it claims is readable back out of it |
| 5 | **Prove** | run the strongest lane available: a test, a walk, a second model | named output, quoted, not described |
| 6 | **Document** | put it where someone who was not here will find it: the page that owns the subject | both site guards pass, and the page renders |
| 7 | **Record** | the decision, its reversal trigger, and what it closed | a dated row exists and the hedges it closed are deleted in the same commit |

## The phases nobody skips, and why they get skipped

| Phase | Why it gets skipped | What it costs |
|---|---|---|
| 1 Understand | the work feels obvious | you build the thing next to the thing that was needed |
| 2 Place | there is an empty file open already | a screen change lands as a record change, and the record is now wrong |
| 5 Prove | it plainly works | a claim with a commit hash and nothing behind it; the next person cannot tell what was verified |
| 6 Document | the build is done | the same question is answered from scratch in three months |
| 7 Record | the decision is obvious now | the hedge stays in the file, and the next session argues the closed question again |

## What makes this loop different from a checklist

Three things, and they are the reason it is a skill rather than a note.

1. **The check comes from the skill set, not from the builder's mood.** Record work is proved by a read-back; screen work by a suite and a live walk; documentation by the guards. The set decides, so the bar cannot quietly drop when the work is tiring.
2. **A failed check is a fork, not a stop.** Fix the work, or change the claim so it is true. Never restate the check.
3. **The loop writes itself down.** Phase 7 is not bookkeeping; it is what lets the loop run again next month without the arguing.

## Running it on more than one thing

When the work is several units, run the loop per unit rather than one loop over everything. Three units of seven phases finish; one unit of twenty-one steps stalls. If two units share a phase 3, that is a sign they are one unit with two outputs.

---
provenance: {author: claude, date: 2026-09-23, session: 8e2713c3, inputs: [the life cycle, screen and documentation work of 2026-09-22 and 2026-09-23 and what actually went wrong in it], review: none by a second model, confidence: high on the phase order, which is how the week's work actually ran}
