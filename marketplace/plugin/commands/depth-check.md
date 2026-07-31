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

4. Write the marker. Markers are SESSION-SCOPED — they live in the session dir, stamped with a `SESSION=` line:

```!
mkdir -p ".claude/sessions/${CLAUDE_CODE_SESSION_ID}" && printf 'DEPTH=N TASK=<slug> SESSION=%s TS=%s\n' "$CLAUDE_CODE_SESSION_ID" "$(date +%s)" > ".claude/sessions/${CLAUDE_CODE_SESSION_ID}/depth-registered"
```

Replace `N` and `<slug>` with the chosen values. (`sutra-marker set depth-registered "DEPTH=N TASK=<slug>"` is equivalent — it resolves the same session dir. The legacy shared global marker is maintained by marker-lib dual-write, never written directly.)

5. Confirm: "Depth gate set. Proceed with the task."
