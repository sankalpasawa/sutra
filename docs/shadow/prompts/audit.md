# Prompt — Shadow Implementation Audit (READ-ONLY)

> Reusable Claude Code prompt. Maps Shadow end-to-end against the canonical
> context document. Produces findings, not changes.
>
> **Output destination:** `docs/shadow/current_state.md`

---

## How to use

Paste everything below the line into Claude Code, in this repository.

Run this before any Shadow implementation or debugging work. `current_state.md`
is empty until this has run at least once.

---

You are performing a **read-only audit** of the Shadow implementation in this
repository.

## Absolute constraint

**Make NO code changes.** No edits, no refactors, no fixes, no file creation, no
"while I was here" cleanups — not even to code that is obviously broken. If you
find something urgent, write it in the report. Reading, searching, and running
read-only commands (`git log`, test listing, type checks) is fine. Do not run
anything that mutates state.

You may write exactly one file: the audit report. Do not modify
`docs/shadow/shadow_context.md`.

## Step 1 — Read the intended behavior

Read `docs/shadow/shadow_context.md` in full. It is the canonical Shadow
product/context reference — what Shadow is *supposed* to be.

Pay particular attention to:

| Section | Why |
|---------|-----|
| §4 The Supervisory Loop | The stages you are auditing against |
| §8 Mission / Task Model | State names and mission fields to look for in code |
| §12 Worker Failure Modes | The detection taxonomy |
| §35 Current vs Future | Which items are claimed as current — verify each one |
| §36 Source Discipline | The labeling rules you must follow |
| §38 Immediate Next Step | The scope of this audit |

Also read `docs/shadow/current_state.md` — if it has been populated before, your
job is to update it, and to note what changed since the last audit.

## Step 2 — Trace Shadow end-to-end

Inspect the **actual implementation**. Follow the real call paths; do not infer
behavior from file or function names.

Trace one full mission from the human's delegation through to completion or
escalation, and record where the code actually lives at each hop.

## Step 3 — Map each area

For every area below: state what the code does, cite `file_path:line`, and give
a classification.

| # | Area | Specifically |
|---|------|--------------|
| 1 | Runtime entrypoints | Where Shadow starts; process/service boundaries; what runs where |
| 2 | Delegation | The `+ Delegate` flow; outcome, `Done when`, work type; what happens on submit |
| 3 | Worker chats | How a worker chat is created, addressed, and driven; what Shadow sends it |
| 4 | Observation | How Shadow sees worker activity — polling, streaming, hooks, transcript reads; what it can and cannot see |
| 5 | Judgment | Where the worker's progress is evaluated; which failure modes from §12 are actually detected |
| 6 | Intervention | How a correction is composed and delivered; whether it is grounded in observed behavior or generic |
| 7 | Completion verification | Whether completion is verified independently, or taken from the worker's claim; how `Done when` is used |
| 8 | Task/mission states | The real state enum; transitions; who triggers each; compare with `READY` / `NEEDS YOU` / `PAUSED` / `FAILED` and any success state |
| 9 | Autonomy | How autonomy level is represented and enforced at runtime |
| 10 | Safety / authority | Safety floors; authority boundaries; what is actually blocked vs merely described |
| 11 | Memory | What persists across missions; what is read back, and where it is injected |
| 12 | Persistence | Storage layer; what survives restart; what is lost |
| 13 | Escalation | How `NEEDS YOU` is raised, surfaced, and cleared; what distinguishes it from `FAILED` |
| 14 | Watch / recurring | Whether watch work exists in runtime or in UI only |
| 15 | Presence / Attention | Whether these are implemented concepts or vocabulary |
| 16 | Budgets / concurrency | Turn counts, budget enforcement, retry, concurrent missions |
| 17 | Tests | Which Shadow behavior is actually covered; run the relevant tests read-only if cheap, and report pass/fail as observed |

## Step 4 — Classify every area

Use exactly these labels:

| Label | Means |
|-------|-------|
| `IMPLEMENTED` | Works end-to-end in the runtime path; you traced it |
| `PARTIAL` | Real code exists, but the behavior is incomplete or only fires on some paths — say which |
| `UI-ONLY` | Present in the interface with no runtime behavior behind it |
| `MOCK` | Hardcoded, stubbed, or fixture-backed |
| `UNCLEAR` | Code exists but you could not determine behavior — say exactly what would resolve it |
| `NOT IMPLEMENTED` | Described in `shadow_context.md`, absent from the code |

Never upgrade a label to be encouraging. `UNCLEAR` is a legitimate result and is
more useful than a guessed `IMPLEMENTED`. Per §36, never silently convert
`INFERENCE → FACT` or `UI concept → implemented behavior`.

## Step 5 — Identify gaps

List every material gap between intended Shadow behavior (`shadow_context.md`)
and actual implementation. For each:

- What the context document says should happen
- What the code does instead
- Evidence: `file_path:line`
- Consequence: what the user experiences because of this gap
- Severity: does this break the core promise (human describes outcome, Shadow
  handles the machinery), or is it a rough edge?

Call out specifically:

1. Anything listed as "current" in §35 that is **not** actually implemented.
2. Any place completion is asserted rather than verified (§13) — false
   completion is the most damaging failure class.
3. Any place `NEEDS YOU` fires for an obstacle Shadow could have resolved (§9).

## Step 6 — Recommend ONE improvement

Exactly one — the highest-leverage change available. Not a list, not a roadmap,
not three ranked options.

State:

- The change, concretely
- Which gap it closes
- Why it is higher-leverage than the alternatives you considered
- Rough size and the files it would touch
- How you would know it worked

Bias toward the change that most reduces required human supervision, since that
is the stated success condition (§2).

## Output

Write the report to `docs/shadow/current_state.md`, using the section headings
already in that file. Keep the four-document distinction intact — this file
records what the code does, not what Shadow should be.

Note in the report the commit SHA and date the audit was run against.

Then summarize in the chat: the classification table, the top gaps, and the one
recommendation.
