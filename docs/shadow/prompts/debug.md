# Prompt — Shadow Debugging

> Reusable Claude Code prompt template for diagnosing a Shadow bug.
>
> Fill in `[BUG / OBSERVED BEHAVIOR]` and `[EXPECTED BEHAVIOR]` before use.

---

## How to use

1. Replace both placeholders below. Be concrete — exact mission text, exact
   state, exact output, what you saw on screen.
2. Paste everything below the line into Claude Code, in this repository.

---

## [BUG / OBSERVED BEHAVIOR]

_What actually happened. Include the mission delegated, the `Done when` if any,
the work type, what Shadow and the worker did, any error text, mission state,
and how to trigger it._

## [EXPECTED BEHAVIOR]

_What should have happened instead, and why you believe that — from
`shadow_context.md`, from a decision, or from your own expectation._

---

You are diagnosing a Shadow bug. **Find the root cause before changing
anything.**

## Step 1 — Establish the intended behavior

Read `docs/shadow/shadow_context.md` — the canonical Shadow product/context
reference — for the sections covering this behavior.

Answer, with citations, before going near the code:

1. What is Shadow *supposed* to do here?
2. Does `shadow_context.md` actually specify it, or is the expectation an
   inference?
3. If the expectation is not specified anywhere, say so — you may be looking at
   an unspecified behavior rather than a bug.

Do not modify this file.

## Step 2 — Establish the current state

Read the relevant sections of `docs/shadow/current_state.md`. Check the
classification of the area involved — a bug report against an area classified
`UI-ONLY`, `MOCK`, or `NOT IMPLEMENTED` is usually a missing feature, not a
defect.

Check `docs/shadow/decisions.md` — the behavior may be a deliberate decision.

Check `docs/shadow/experiments.md` — this may have been seen before.

If `current_state.md` is still an unpopulated placeholder, say so and inspect
the code directly.

## Step 3 — Reproduce and trace

Reproduce it if you can. If you cannot, say so — do not proceed on a theory you
never observed.

Then trace the actual execution path: entry point → each hop → the point where
behavior diverges from expected. Cite `file_path:line` at each step.

Read the code. Do not infer behavior from names, comments, or documentation —
all three can be stale.

## Step 4 — Classify before fixing

Decide which of these you are looking at, and say which:

| Classification | Means | Right response |
|----------------|-------|----------------|
| **Implementation bug** | Code does not do what it was built to do | Fix the code |
| **Product misunderstanding** | Code works as designed; the expectation was wrong | Do not "fix" it — explain, and propose a `decisions.md` entry if the expectation should become the rule |
| **Unspecified behavior** | Nobody decided what should happen here | Surface the gap; a decision is needed before a fix |
| **Stale documentation** | Code is right, a document is wrong | Say which document, propose the correction, do not touch the code |

Getting this wrong is expensive: "fixing" intended behavior introduces a real
bug while closing a false one. If the user's stated expectation is wrong, say so
directly.

## Step 5 — State the root cause

Before any edit:

- **Root cause:** the actual mechanism, at `file_path:line` — not the symptom,
  and not "something in X seems off"
- **Why it produces this symptom:** the causal chain
- **Confidence:** high / moderate / low / unknown
- **What would disprove this:** name it

If confidence is low, say so and keep investigating rather than fixing on a
hunch. A confident wrong fix is worse than an honest "I have not found it yet."

## Step 6 — Propose the smallest fix

State the fix before making it: what changes, why it addresses the root cause
rather than the symptom, and what else it could affect.

| Do | Do not |
|----|--------|
| Fix the root cause | Patch the symptom to make it look right |
| Touch only what the fix requires | Refactor while you are in there |
| Note other problems in the report | Fix unrelated bugs silently |

Do not weaken a safety boundary to make a bug go away — safety floors, autonomy
enforcement, escalation paths, and completion verification (`shadow_context.md`
§13–§15, §23) all stay intact. Suppressing an escalation or loosening completion
verification turns a visible bug into an invisible one.

## Step 7 — Run relevant tests

Run the tests covering the fixed path plus anything downstream. Focused set, not
the full suite, unless asked.

Add a test that reproduces this bug where a reasonable place to put one exists —
a bug that can silently return is not fully fixed.

Report results as observed, including failures. Note pre-existing failures as
pre-existing and leave them alone.

## Step 8 — Report

- **Symptom** → **Root cause** (`file_path:line`) → **Fix**
- **Classification** from Step 4
- **Files changed**, one line each
- **Tests run**, with actual results; new test added or why not
- **Verified vs assumed** — kept as two separate lists. Say explicitly whether
  you reproduced the bug and confirmed the fix resolves it, or are reasoning
  from code alone
- **Not fixed** — anything you found and deliberately left, and why
- **Documentation** — whether this warrants an update to `current_state.md`,
  `decisions.md`, or `experiments.md`. Do not update them unasked

Do not commit or push unless asked.
