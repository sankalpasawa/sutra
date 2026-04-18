---
name: depth-estimation
description: Use at the start of any multi-step task, before tool calls. Assigns a depth rating (1-5) and emits a 5-line estimation block (TASK / DEPTH / EFFORT / COST / IMPACT). Writes a depth marker to .claude/depth-registered for the pretool hook to verify.
---

# Depth Estimation

Every task gets a depth rating before work begins. Depth is how exhaustive the analysis should be — not complexity.

## The block

Emit this verbatim before starting any task:

```
TASK: "[what you're about to do]"
DEPTH: X/5 (surface|considered|thorough|rigorous|exhaustive)
EFFORT: [time estimate], [files estimate]
COST: ~$X (~Y% of session budget)
IMPACT: [what this changes and for whom]
```

## Depth scale

| Depth | Label       | When                                           |
|:-----:|-------------|------------------------------------------------|
| 1     | surface     | Trivial edits, single-file renames, comment fixes |
| 2     | considered  | Small features, isolated logic changes, <3 files |
| 3     | thorough    | Multi-file changes, moderate logic, needs review |
| 4     | rigorous    | Architectural changes, migrations, cross-cutting |
| 5     | exhaustive  | Foundational work, OS-level decisions, irreversible |

## Depth marker

After emitting the block, write the marker so the pretool hook can verify it exists before Edit/Write:

```bash
mkdir -p .claude && echo "DEPTH=N TASK=<slug> TS=$(date +%s)" > .claude/depth-registered
```

Replace `N` with the chosen depth and `<slug>` with a short task identifier.

## Post-task triage

After completing the task, log whether the depth was correct:

```
TRIAGE: depth_selected=X, depth_correct=X, class=[correct|overtriage|undertriage]
```

Over time this shows whether the system habitually over- or under-triages.

## Rule of thumb

Default to depth 2-3 for most work. Jump to 4-5 only for architectural or cross-cutting changes. Drop to 1 only for trivial touches. If you can't decide between two depths, pick the higher one.
