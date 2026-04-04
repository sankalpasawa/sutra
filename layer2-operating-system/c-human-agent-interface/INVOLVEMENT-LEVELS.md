# Human-Agent Involvement Levels

## What This Is

Defines how much the human (founder/CEO) wants to be involved in day-to-day decisions. Set during onboarding (CLIENT-ONBOARDING.md, Question 11). Stored in the company's SUTRA-CONFIG.md.

## The Three Levels

### Hands-on

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

### Strategic

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

### Delegated

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

## Override

The human can always override, regardless of level. "I want to see this before you ship" is always valid, even in Delegated mode. See SOVEREIGNTY.md.

## How It's Stored

In the company's `SUTRA-CONFIG.md`:

```yaml
founder_involvement: "hands-on"  # or "strategic" or "delegated"
```

## Default

**Strategic**. If the founder doesn't specify, Sutra defaults to Strategic — the middle ground.
