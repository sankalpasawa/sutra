# Human-Agent Interface

This document defines how humans and AI agents collaborate: authority boundaries, involvement levels, input routing, and override protocols.

---

## Part 1: Human Sovereignty Model

Defines the boundary between human authority and agent authority. Derived from Asawa's HUMAN-AI-INTERACTION.md principles 1, 4, and 7.

### The Core Contract

```
WHAT to build  = HUMAN (product, strategy, taste, priorities, business decisions)
HOW to build   = AGENT (execution, tool choice, file structure, code patterns)
WHEN to stop   = HUMAN (always has override, always has final say)
```

### What the Human Owns

| Domain | Examples | Agent Behavior |
|--------|----------|----------------|
| **Product** | What features to build, what to kill, what to prioritize | Agent presents options. Human decides. |
| **Strategy** | Market positioning, pricing, partnerships, go-to-market | Agent provides data. Human decides direction. |
| **Taste** | Visual aesthetics, brand voice, UX feel | Agent executes. Human approves. No amount of data overrides taste. |
| **Business** | Spending, hiring, legal, partnerships | Agent never decides. Always escalates. |
| **Risk** | What risks to accept, what to mitigate | Agent identifies risks. Human accepts or rejects. |

### What the Agent Owns

| Domain | Examples | Human Involvement |
|--------|----------|-------------------|
| **Execution** | Which file to edit, how to structure code, which tool to use | None (unless human wants to override) |
| **Process** | Which process to follow, which steps to execute, how to run QA | None (process is pre-defined, agent follows it) |
| **Tool choice** | Which skill to invoke, which agent to spawn, how to parallelize | None |
| **Technical** | Database schema implementation, API design, error handling | Human reviews if crosses architecture boundary |

### The Override Protocol

From Asawa's ENFORCEMENT-FRAMEWORK.md:

1. Human says "bypass {hook}" or "skip the process" — this is an **explicit override**
2. Agent creates `.enforcement/override-{hook-name}` with reason and timestamp
3. Hook checks for override file — allows the action
4. Override is logged to audit trail
5. Override expires after 1 hour
6. All overrides surface in weekly review

**Key rules:**
- Only the HUMAN can request an override. Agent never bypasses on its own.
- Override is scoped to ONE hook. "Bypass process-gate" doesn't bypass self-assessment.
- Override is time-limited. The gate re-engages after 1 hour.
- Every override is logged. No silent bypasses.

### Natural Language Is Intent, Not Override

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

### The Watchmen Problem

Who enforces sovereignty over the enforcer? Answer:

1. **Hooks enforce agents** (hard gates, can't bypass without override)
2. **Humans enforce hooks** (can override any hook, logged)
3. **Weekly review enforces humans** (are overrides reasonable? too frequent?)
4. **Founder enforces weekly review** (Sankalp is the final authority)

The chain terminates at the human. This is by design.

---

## Part 2: Involvement Levels

Defines how much the human (founder/CEO) wants to be involved in day-to-day decisions. Set during onboarding (CLIENT-ONBOARDING.md, Question 11). Stored in the company's SUTRA-CONFIG.md.

### The Three Levels

#### Hands-on

"I want to decide everything."

| Aspect | Behavior |
|--------|----------|
| Product decisions | Agent presents options, human picks |
| Design decisions | Agent shows mockups, human approves |
| Architecture | Agent proposes, human reviews before implementation |
| Shipping | Agent prepares, human approves before deploy |
| Bug fixes | Agent diagnoses, human approves fix approach |
| Process | Full pipeline (SUTRA mode) by default |

**When to use**: Early-stage products, design-sensitive work, founder learning the system.

#### Strategic

"I decide direction, you handle execution."

| Aspect | Behavior |
|--------|----------|
| Product decisions | Human sets priorities, agent executes without approval per feature |
| Design decisions | Agent follows DESIGN.md, only escalates taste decisions |
| Architecture | Agent decides within established patterns, escalates novel patterns |
| Shipping | Agent ships autonomously, human reviews post-deploy |
| Bug fixes | Agent fixes and ships, notifies human |
| Process | Agent chooses SUTRA or DIRECT mode per feature based on complexity |

**When to use**: Established products with clear design system, trusted agent-founder relationship.

#### Delegated

"Just build it. Show me when it's done."

| Aspect | Behavior |
|--------|----------|
| Product decisions | Agent follows TODO.md top-down, human reviews weekly |
| Design decisions | Agent decides, human sees in weekly review |
| Architecture | Agent decides, documents in decision log |
| Shipping | Autonomous. Human gets weekly summary. |
| Bug fixes | Autonomous. Human gets incident report only for P0/P1. |
| Process | DIRECT mode unless agent judges SUTRA mode is needed |

**When to use**: Mature products, well-defined roadmaps, founder focused elsewhere.

### Founder Role Evolution

| Portfolio Size | Founder Role | Time Split |
|---------------|-------------|-----------|
| 1-3 companies | Builder — hands-on in every company | 70% building, 30% governance |
| 4-7 companies | Director — sets direction, reviews output | 30% building, 70% governance |
| 8+ companies | Allocator — capital allocation, talent placement, strategy | 10% building, 90% governance |

The shift is gradual. PROTO-015 fires a reminder when the founder is spending >50% time operating a single company.

From Andrew Wilkinson (Tiny): "You must be the owner, not the CEO of each business."
From Warren Buffett: "I tap dance to work. But I don't do the work at the subsidiaries."

### Override

The human can always override, regardless of level. "I want to see this before you ship" is always valid, even in Delegated mode.

### How It's Stored

In the company's `SUTRA-CONFIG.md`:

```yaml
founder_involvement: "hands-on"  # or "strategic" or "delegated"
```

**Default: Strategic.** If the founder doesn't specify, Sutra defaults to Strategic.

---

## Part 3: Input Routing Protocol

Every human input is input TO the system, not a command to the LLM. The system classifies, routes, checks fit, then acts. The LLM does not decide what to do with input — the routing layer does.

### Classification Block

Before any action, the LLM outputs:

```
INPUT: [what the founder said]
TYPE: direction | task | feedback | new concept | question
EXISTING HOME: [where this already lives in the system, or "none"]
ROUTE: [which protocol handles this]
FIT CHECK: [what changes in existing architecture]
ACTION: [proposed action — only after the above]
```

This block is mandatory. No action proceeds without it.

### Classification Types and Routing

| Type | Route |
|------|-------|
| **direction** | `FOUNDER-DIRECTIONS.md`. Model implications across the system. Cascade changes to all affected protocols and companies. |
| **task** | `TASK-LIFECYCLE.md`. Estimate scope and effort. Execute through the standard lifecycle. |
| **feedback** | Capture verbatim. Route to the relevant protocol, company, or layer. Feed into the next review cycle. |
| **new concept** | `NEW-THING-PROTOCOL.md`. Classify the concept. Determine where it integrates into existing architecture before building anything. |
| **question** | Answer from existing knowledge. Cite the source document or protocol. If the answer does not exist in the system, say so. |

### Enforcement Levels

Companies choose which enforcement levels to run. Higher levels are harder to bypass.

| Level | Name | How It Works |
|-------|------|-------------|
| **Level 1** | Hook Gate (hardest) | PreToolUse hook blocks Write/Edit until a classification marker exists. Mechanical enforcement — no willpower required. |
| **Level 2** | Protocol (medium) | CLAUDE.md instruction requires the LLM to output the classification block. Relies on the LLM following instructions. |
| **Level 3** | Skill (architectural) | A skill fires on every input, performs classification and routing automatically. |

Companies can run multiple levels. Asawa runs all three.

### Whitelisted Actions

The following skip classification entirely — they are system maintenance, not responses to input:

- Memory file writes (`memory/`)
- Checkpoint files (`checkpoints/`)
- TODO checkbox toggles (`TODO.md`)
- Git operations (commit, push)
- Lock files (`.lock`)

### Key Principle

> The LLM is the runtime that executes the system's protocols. It is never the first responder. The routing layer is the first responder.
