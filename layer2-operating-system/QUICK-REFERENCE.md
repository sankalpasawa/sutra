# Sutra Quick Reference — For Company Sessions

Read this instead of the full engine specs. Takes 30 seconds.

## Before Every Task

### Step 1: Estimate (2 min)
How confident are you? How many files? How long?

| Dimension | Quick Answer |
|-----------|-------------|
| Confidence | High (>80%) / Medium (50-80%) / Low (<50%) |
| Files | Count them |
| Time | Use multiplier: config=0.3x, UI=0.45x, security=0.8x of your gut estimate |

If confidence < 40% or cost > $5 tokens: flag to founder.

### Step 2: Pick Depth
Score the task 1-5 on: impact, sensitivity, complexity.
Take the MAX score:

| Max Score | Depth | Pipeline |
|-----------|-------|----------|
| 1-2 | Minimal | build → ship → log |
| 3 | Standard | estimate → build → test → ship → learn |
| 4 | Full | estimate → SPEC → build → test → review → ship → learn |
| 5 | Critical | estimate → SPEC → review → build → verify → ship → learn → retro |

### Step 3: Build at that depth
Follow the pipeline. No more, no less.

### Step 4: Log
Append actuals to engines/estimation-log.jsonl.

## That's it.
Full specs in engines/ if you need them. You probably don't.
