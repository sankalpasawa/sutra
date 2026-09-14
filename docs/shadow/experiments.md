# Shadow — Experiments

> Dogfooding and product experiments used to improve Shadow.

---

## Status: NO EXPERIMENTS RECORDED YET

This log starts empty on purpose. Entries are written from **observed runs** —
an actual mission delegated to Shadow and watched end to end.

**Do not invent experiments, and do not write an entry from what Shadow
probably would have done.** An entry with no run behind it contaminates the one
source of real evidence in this workspace.

### What an experiment is for

Per `shadow_context.md` §2, the success condition is not "Shadow can run an AI"
— it is whether Shadow reduces the human supervision needed to reliably reach
an outcome. Each entry should make that measurable for one mission: what the
human had to do, and what Shadow handled alone.

### Relationship to the other documents

| Document | Answers |
|----------|---------|
| `shadow_context.md` | What we believe Shadow is supposed to be |
| `current_state.md` | What the code actually does |
| `decisions.md` | What we have explicitly decided |
| `experiments.md` (this file) | What we learned from using Shadow |
| `prompts/` | Reusable instructions for Claude Code |

An experiment that produces a rule goes to `decisions.md`. An experiment that
reveals what the code really does goes to `current_state.md`. This file keeps
the raw observation.

---

## Experiment Template

Copy this block per run. Newest first.

### Date

When the run happened, and the commit or build Shadow was running.

### Mission

The exact outcome delegated, verbatim — including `Done when` if one was given,
and the work type (fix / feature / research / watch / custom).

### Intended Outcome

What success would have looked like, written **before** the run.

### What Happened

A factual trace of the run. No interpretation.

### Worker Behavior

What the worker did — planning, execution, tool use, claims of completion.

### Shadow Behavior

What Shadow did as supervisor — what it observed, how it judged, whether and
when it intervened, how it verified, whether it escalated.

### Human Intervention

Every point the human had to step in, and why. This is the core metric: count
it, and note which interventions Shadow should have handled itself.

### What Worked

### What Failed

### Failure Category

Use the taxonomy in `shadow_context.md` §12:

| Code | Failure mode |
|------|--------------|
| A | Over-planning |
| B | Stuckness |
| C | Loops |
| D | Goal drift |
| E | Misunderstanding |
| F | Premature completion |
| G | Low-quality completion |
| H | Missing capability |
| I | Human dependency |

Add `SHADOW-*` categories for supervisor-side failures (missed detection, bad
intervention, false completion, false escalation). Note when a failure fits
nothing in the taxonomy — that is a finding about the taxonomy.

### Product Insight

What this run says about Shadow that was not known before.

### Proposed Change

One change. Per `shadow_context.md` §39, avoid solving every future problem at
once.

### Result After Change

Filled in after the change ships and the mission is re-run. Note if the change
made things worse — that is the most useful entry in the log.

---

_No entries yet._
