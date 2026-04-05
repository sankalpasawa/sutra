# Sutra — Process Generation Protocol

ENFORCEMENT: HARD — applies whenever an agent encounters work with no existing process.

## The Core Principle

When you encounter something Sutra doesn't have a process for, you don't wing it.
You don't skip process. You CREATE a process, then follow it.

## How It Works

```
1. DETECT: "There's no Sutra process for this."
2. THINK: "How should this be approached? What are the sub-steps?"
3. CREATE: Write a lightweight process (inline or as a file, depending on reuse value)
4. FOLLOW: Execute using the process you just created
5. FEEDBACK: After execution, evaluate — was the process useful? Feed back to Sutra.
```

## Process Depth (matches Adaptive Protocol Engine)

Not everything needs a 50-line protocol. Depth scales with complexity:

| Complexity | Process Format | Example |
|-----------|---------------|---------|
| Trivial (L1) | Mental checklist — 2-3 steps in the commit message | "Fix: read error → find cause → fix → verify" |
| Standard (L2) | Inline markdown block in the feature artifact | 5-10 steps in SPEC.md |
| Complex (L3) | Standalone process file in os/processes/ | Full process with inputs, steps, outputs, gates |
| Critical (L4) | Sutra-level protocol candidate | Goes through PROTOCOL-CREATION.md lifecycle |

## Nested Processes

Complex work decomposes into sub-processes. Each sub-process follows the same pattern:

```
Process: "Deploy to Android"
├── Sub-process: "Configure EAS Build"
│   ├── Step: Read Expo EAS docs
│   ├── Step: Create eas.json
│   └── Step: Test build locally
├── Sub-process: "Play Store Setup"
│   ├── Step: Create developer account
│   ├── Step: Generate signing key
│   └── Step: Upload AAB
└── Sub-process: "Verify"
    ├── Step: Install from Play Store
    └── Step: Test core flows
```

Depth of nesting = complexity of the problem (as scored by Adaptive Protocol Engine).

## When to Feed Back to Sutra

After executing a generated process, ask:

| Question | If YES |
|----------|--------|
| Will this situation recur across companies? | Promote to Sutra protocol (via PROTOCOL-CREATION.md) |
| Will this recur within this company? | Save as company-level process in os/processes/ |
| Was this a one-time thing? | Discard — don't accumulate process debt |

## The Anti-Pattern

"I've never done this before, so I'll just figure it out as I go."

This is how knowledge gets lost between sessions. The process you create — even a 3-line one —
is the artifact that makes the next session smarter.

## Integration with Evolution Cycles

Every gap report should note:
- "Was there a missing process?" → If yes, was one generated on the fly?
- "Was the generated process useful?" → If yes, should it be promoted?
- "Was the process too heavy for the problem?" → If yes, reduce depth next time.
