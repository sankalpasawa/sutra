---
name: depth-check
description: Manually emit a Depth + Estimation block for the next task. Writes the depth marker. Use when the auto-skill didn't trigger or you want to set depth explicitly.
disable-model-invocation: false
argument-hint: [task description]
---

# /depth-check — Manual Depth Gate

Emit a depth + estimation block for the task in $ARGUMENTS, then write the depth marker.

## Steps

1. Read $ARGUMENTS. If empty, ask the user: "What task do you want a depth read on?"
2. Assess depth using the scale:
   - 1 surface / 2 considered / 3 thorough / 4 rigorous / 5 exhaustive
3. Emit:

```
TASK: "$ARGUMENTS"
DEPTH: X/5 ([label])
EFFORT: [time estimate], [files estimate]
COST: ~$X (~Y% of session budget)
IMPACT: [what this changes and for whom]
```

4. Write the marker:

```!
mkdir -p .claude && echo "DEPTH=N TASK=<slug> TS=$(date +%s)" > .claude/depth-registered
```

Replace `N` and `<slug>` with the chosen values.

5. Confirm: "Depth gate set. Proceed with the task."
