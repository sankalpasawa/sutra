# DEPTH — Every task gets assessed before you start

Sutra asks you to rate every task on a 1-5 scale before acting:

| Depth | Meaning                | Example                                         |
|-------|------------------------|-------------------------------------------------|
| 1     | Surface / trivial      | Rename a variable. Add a comment.               |
| 2     | Considered             | Fix a small bug you understand.                 |
| 3     | Thorough               | Refactor a function. Change behavior carefully. |
| 4     | Rigorous               | Cross-cutting change. Need tests + review.      |
| 5     | Exhaustive             | Infrastructure. Governance. Breaking changes.   |

## Why this exists

Time and attention are the scarcest resources. Depth-rating forces you to *choose* how much care a task deserves BEFORE you start. When you over-triage (depth 5 for a one-line fix), you burn attention. When you under-triage (depth 1 for a cross-cutting migration), you break production.

Writing the depth down BEFORE acting makes the choice visible. Visible choices get examined. Examined choices get better.

## How Sutra enforces it

Before Edit/Write, the depth-marker hook checks `.claude/depth-registered`. If it's missing, you get a block with:

```
BLOCKED — DEPTH BLOCK MISSING
  Emit before any Write/Edit: TASK / DEPTH / EFFORT / COST / IMPACT
```

At **level L0 (novice)**, the block message includes explanation ("why this matters, how to write a depth block"). At **L3 (master)**, it's terse.

## Relation to other charters

- **TOKENS** charter: depth drives token budget allocation.
- **SPEED** charter: depth determines time investment (D1 = minutes, D5 = hours).
- **PRIVACY** charter: sanitization fail-closed rate is always D5.
