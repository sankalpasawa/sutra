---
name: input-routing
description: Use on every user message — NO topic exemptions. Personal, research, non-coding, emotional, chitchat all receive identical routing block. Emits 5-line routing block (TYPE/HOME/ROUTE/FIT/ACTION) classifying direction/task/feedback/new-concept/question. Structure universality, not depth universality — for lightweight inputs, keep field content minimal but never omit the block. Per founder direction "sutra for anything and everything" (D45-candidate, 2026-05-03).
---

# Input Routing

Every user input gets classified before the system acts. The block is mandatory before any tool call.

## The block

Emit this verbatim structure as the first text in your response, before any reasoning or tool use.

```
INPUT: [paraphrase of what the user said]
TYPE: direction | task | feedback | new concept | question
EXISTING HOME: [where this already lives, or "none"]
ROUTE: [which protocol / file / workflow handles this]
FIT CHECK: [what changes in existing architecture, or "no change"]
ACTION: [proposed next action]
```

## Type definitions

- **direction** — an instruction that changes how future work is done (e.g., "always X", "don't Y")
- **task** — a request for specific work (code, research, doc)
- **feedback** — a correction or validation of prior output
- **new concept** — no existing home; needs a new-thing protocol before building
- **question** — information request, not an action

## Rules

- Mandatory before any `Write`, `Edit`, or creation action
- Whitelisted (skip classification): memory files, checkpoints, TODO checkboxes, git operations
- TYPE = "new concept" → route through a new-thing protocol before building
- TYPE = "direction" → log to the project's directions file and model implications before acting
- The LLM is the runtime. It is never the first responder.

## Compact form (lightweight turns)

For zero/low-risk turns (single read-only call, pure question, trivial reply), use the 3-field compact form. Structure stays per "structure universality" — fields just collapse.

```
INPUT (TYPE): [paraphrase]
ROUTE: [where this goes]
ACTION: [next action]
```

Skip EXISTING HOME when "none" or obvious. Skip FIT CHECK when "no change". Both still implied.

Use compact form when:
- Turn is a question (no tool calls planned)
- Turn is a single read-only call (Read, Grep, Glob, BashOutput) with no follow-up
- Turn is a trivial confirmation (e.g., "yes", "correct")

Use full 6-field form when:
- Tool calls will mutate state (Edit/Write/MultiEdit)
- Multi-step plan with branching
- Founder direction that changes future-work rules
- New concept needing routing through new-thing protocol

Per D-UX-2 codex ADVISORY 2026-05-04 + Q4 fold (zero/low-risk turn rule).

## Self-check

After emitting the block, ask: does ROUTE point to an existing, named thing? If not, you classified a new concept as a task — reclassify.
