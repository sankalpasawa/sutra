# Input Routing — How Sutra classifies what you say

Every founder message gets classified before Sutra acts on it. The routing block looks like this:

```
INPUT: [the founder said]
TYPE: direction | task | feedback | new concept | question
EXISTING HOME: [where this already lives]
ROUTE: [which protocol handles it]
FIT CHECK: [what changes in existing architecture]
ACTION: [proposed action]
```

## The 5 types

| Type          | Signal                                         | Route                         |
|---------------|------------------------------------------------|-------------------------------|
| direction     | Founder says how you should work               | FOUNDER-DIRECTIONS.md append  |
| task          | Concrete thing to do                           | execute with depth            |
| feedback      | Correction or confirmation                     | adjust behavior               |
| new concept   | Something Sutra has not encountered            | NEW-THING-PROTOCOL.md         |
| question      | Founder wants information                      | answer, no side effects       |

## Why this exists

Most mistakes come from misclassifying the input. If you treat a direction as a task, you do the wrong thing once and never learn. If you treat feedback as a new concept, you over-architect. Routing makes classification explicit.

## How Sutra enforces it

Before any Edit/Write, a hook checks `.claude/input-routed`. Missing → blocked. The routing block is output text, but the marker proves you wrote it.

Whitelist (skip classification): memory files, checkpoints, TODO checkboxes, git operations.

## Related charters

- **PEDAGOGY**: at L0, routing explanations are verbose. At L3, one-line summary is enough.
- **TOKENS**: routing adds ~150 tokens per turn. Budget accounts for it.
