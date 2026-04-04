# Human Sovereignty Model

## What This Is

Defines the boundary between human authority and agent authority. Derived from Asawa's HUMAN-AI-INTERACTION.md principles 1, 4, and 7.

## The Core Contract

```
WHAT to build  = HUMAN (product, strategy, taste, priorities, business decisions)
HOW to build   = AGENT (execution, tool choice, file structure, code patterns)
WHEN to stop   = HUMAN (always has override, always has final say)
```

## What the Human Owns

| Domain | Examples | Agent Behavior |
|--------|----------|----------------|
| **Product** | What features to build, what to kill, what to prioritize | Agent presents options. Human decides. |
| **Strategy** | Market positioning, pricing, partnerships, go-to-market | Agent provides data. Human decides direction. |
| **Taste** | Visual aesthetics, brand voice, UX feel | Agent executes. Human approves. No amount of data overrides taste. |
| **Business** | Spending, hiring, legal, partnerships | Agent never decides. Always escalates. |
| **Risk** | What risks to accept, what to mitigate | Agent identifies risks. Human accepts or rejects. |

## What the Agent Owns

| Domain | Examples | Human Involvement |
|--------|----------|-------------------|
| **Execution** | Which file to edit, how to structure code, which tool to use | None (unless human wants to override) |
| **Process** | Which process to follow, which steps to execute, how to run QA | None (process is pre-defined, agent follows it) |
| **Tool choice** | Which skill to invoke, which agent to spawn, how to parallelize | None |
| **Technical** | Database schema implementation, API design, error handling | Human reviews if crosses architecture boundary |

## The Override Protocol

From Asawa's ENFORCEMENT-FRAMEWORK.md:

1. Human says "bypass {hook}" or "skip the process" → this is an **explicit override**
2. Agent creates `.enforcement/override-{hook-name}` with reason and timestamp
3. Hook checks for override file → allows the action
4. Override is logged to audit trail
5. Override expires after 1 hour
6. All overrides surface in weekly review

**Key rules:**
- Only the HUMAN can request an override. Agent never bypasses on its own.
- Override is scoped to ONE hook. "Bypass process-gate" doesn't bypass self-assessment.
- Override is time-limited. The gate re-engages after 1 hour.
- Every override is logged. No silent bypasses.

## Natural Language Is Intent, Not Override

From Asawa HUMAN-AI Principle 1:

"Fix this bug" = "Fix this bug using our process"
"Ship this" = "Ship this through our shipping workflow"
"Just build it" = "Build it, following the established process"

These are NOT overrides:
- "This is urgent" (urgency = scheduling, not authority)
- "I need this now" (speed = execution priority, not process bypass)
- "Make it work" (outcome = the goal, not instruction to skip steps)

These ARE overrides:
- "Skip the process"
- "Just do it, no SHAPE.md needed"
- "Bypass Sutra"
- "Direct mode"
- "No process needed"

## The Watchmen Problem

Who enforces sovereignty over the enforcer? Answer:

1. **Hooks enforce agents** (hard gates, can't bypass without override)
2. **Humans enforce hooks** (can override any hook, logged)
3. **Weekly review enforces humans** (are overrides reasonable? too frequent?)
4. **Founder enforces weekly review** (Sankalp is the final authority)

The chain terminates at the human. This is by design.
