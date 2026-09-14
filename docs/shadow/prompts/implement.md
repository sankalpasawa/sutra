# Prompt — Shadow Implementation

> Reusable Claude Code prompt template for making a change to Shadow.
>
> Fill in `[TASK TO IMPLEMENT]` before use.

---

## How to use

1. Replace `[TASK TO IMPLEMENT]` with the actual task.
2. Paste everything below the line into Claude Code, in this repository.

Prerequisite: `docs/shadow/current_state.md` should be populated (run
`prompts/audit.md` first). If it is still a placeholder, say so and inspect the
code directly rather than treating the empty sections as "nothing exists."

---

## Task

[TASK TO IMPLEMENT]

---

You are implementing a change to Shadow. Work in this order and do not skip
ahead to the code.

## Step 1 — Read the intended behavior

Read `docs/shadow/shadow_context.md` — the canonical Shadow product/context
reference. Read the sections relevant to this task closely, and at minimum:

- §4 The Supervisory Loop
- §15 Safety Floors
- §36 Source Discipline
- §34 What Not to Build Prematurely

Do not modify this file. It describes intent, not implementation.

## Step 2 — Read the current state

Read the relevant sections of `docs/shadow/current_state.md` — what the code
actually does today, with its classifications.

Treat it as a map, not as truth: it was accurate when the audit ran, and the
code may have moved since. Verify anything you rely on.

Also check `docs/shadow/decisions.md` for a decision that already constrains
this task. If one exists, follow it. If this task contradicts it, stop and say
so before writing code.

## Step 3 — Inspect the existing implementation

Before writing anything, read the actual code you are about to change and the
code that calls it. Find:

- Where this behavior lives now, if it exists at all
- Existing patterns for this kind of thing in the codebase — match them
- What else calls into the code you are about to touch
- The tests that currently cover it

An implementation that ignores the surrounding conventions is a worse result
than a slightly less elegant one that fits.

## Step 4 — Explain the change before making it

State clearly, before editing:

| | |
|---|---|
| **What you will change** | Files and functions |
| **Why this approach** | And what you rejected |
| **Blast radius** | What else this touches or could break |
| **Assumptions** | Anything you inferred rather than verified |
| **Safety impact** | See Step 6 |

If the task as stated is the wrong thing to build, say so in a sentence or two
— then build what was asked, under stated assumptions. Scaling the work down is
the human's call.

If a genuine ambiguity would change the implementation materially, ask. If it
would not, pick the sensible default, state it, and proceed.

## Step 5 — Make the smallest appropriate change

| Do | Do not |
|----|--------|
| Change what the task requires | Refactor unrelated code |
| Follow existing patterns | Introduce a new pattern, abstraction layer, or dependency without saying why |
| Fix the specific problem | Rename, reformat, or reorganize code you happened to open |
| Note unrelated problems in the report | Fix them silently in the same change |

"Smallest appropriate" is not "smallest possible" — do the task completely. If
part of it is blocked, finish everything else and say explicitly what you left
out and why.

Do not install dependencies or change configuration unless the task requires it
and you flagged it in Step 4.

## Step 6 — Preserve Shadow's safety boundaries

Shadow acts on a human's behalf. Do not weaken, bypass, or widen any of the
following as a side effect of this change:

- Safety floors (`shadow_context.md` §15) and authority boundaries
- The autonomy level a mission runs under (§14)
- Escalation paths — a condition requiring human authority must still reach
  `NEEDS YOU` (§9, §23)
- Completion verification — do not make Shadow easier to satisfy. Accepting a
  worker's claim of completion as evidence is a regression (§13)

If the task genuinely requires changing a safety boundary, stop and raise it
explicitly. Do not do it inside a larger change.

## Step 7 — Run relevant tests

Run the tests covering what you changed, plus anything downstream that could
break. Run the focused set, not the full suite, unless asked for the full suite.

Report results as observed. If a test fails, say so and show the output. If a
failure is pre-existing, say that — and do not chase it into unrelated fixes.
If no test covers this behavior, say so plainly rather than reporting a pass
that means nothing.

## Step 8 — Report

Finish with:

### Files changed
`path` — what changed and why. One line each.

### Tests run
Command, result, and the actual output for anything that failed. Note
pre-existing failures separately from ones you caused.

### Implemented vs assumed

Two explicit lists. Keep them separate:

| | |
|---|---|
| **Implemented** | Behavior you wrote and verified — say how you verified it |
| **Assumed** | Anything you inferred, could not verify, or took on faith from docs |

Never state an assumption as a verified fact. If you did not run it, say you did
not run it.

### Follow-ups
Anything you deliberately left alone, including problems you found and did not
fix.

### Documentation
Say which of these the change warrants — do not update them unasked:

| Document | Update when |
|----------|-------------|
| `current_state.md` | The change makes a section of it inaccurate |
| `decisions.md` | The change embodies a decision worth recording |

Do not commit or push unless asked.
