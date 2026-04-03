# Sutra (सूत्र) — Vision

## What Sutra Is
Sutra is a living operating system for companies. Not documentation. Not a framework you read once. A system that actively pushes updates to client companies and learns from their feedback.

## The Two-Way Loop

```
SUTRA
  │ Pushes: principles, operating model, sensors, functional guidelines
  ▼
CLIENT COMPANY (e.g., DayFlow)
  │ Implements. Runs. Encounters reality.
  │ Feeds back: incidents, violations, new problem types, what works
  ▼
SUTRA
  │ Learns. Updates. Pushes refined model to ALL clients.
  ▼
(cycle continues — both get smarter)
```

## How It Works with Agents

### Sutra-Side Agents
- **Publisher**: When Sutra's operating model or principles change, pushes updates to all client company folders. Adapts generic principles to each client's specific context.
- **Learner**: Reads feedback from all client companies. Identifies cross-company patterns. "DayFlow hit this bug. Would CompanyB hit it too?" Proposes principle updates.
- **Researcher**: Continuously studies new books, frameworks, company practices. Feeds findings into the operating model.

### Client-Side Agents (deployed by Sutra into each client company)
- **Executor**: Runs using Sutra's operating model. Follows the Sense→Shape→Decide→Specify→Execute→Learn flow.
- **Reporter**: When a bug, edge case, principle violation, or new problem type is discovered, automatically logs it and feeds it back to Sutra.
- **Adapter**: Takes generic Sutra principles and adapts them to the client's specific domain, codebase, and business context.

### The Feedback Types (Client → Sutra)
1. **Incident report**: "This principle didn't prevent this bug. Here's what happened."
2. **Principle violation**: "We violated principle X because it conflicted with reality Y."
3. **New problem type**: "We encountered a problem that no existing principle covers."
4. **Validation**: "Principle X worked exactly as designed. Confirmed useful."
5. **Adaptation**: "We had to modify principle X for our context. Here's how."

### The Push Types (Sutra → Client)
1. **New principle**: "Based on cross-company learning, here's a new principle."
2. **Updated principle**: "Principle X was refined based on feedback from 3 clients."
3. **New sensor**: "Based on incidents, here's a new automated check to add."
4. **New functional guideline**: "The security function now requires this additional check."
5. **Operating model update**: "The Specify stage now includes this additional step."

## The Self-Improving Property
Each client company that uses Sutra makes Sutra better for ALL client companies. The more companies use it, the more feedback Sutra gets, the better the principles become, the more valuable it is for every client. This is a network effect on organizational knowledge.

## First Client: DayFlow
DayFlow is the first implementation. Everything Sutra learns from DayFlow becomes available to future client companies. DayFlow's bugs, edge cases, and discoveries are Sutra's training data.

## File Structure
```
asawa-inc/
├── sutra/                    — The method company
│   ├── VISION.md             — This file
│   ├── OPERATING-MODEL.md    — The generic operating model
│   ├── PRINCIPLES-BY-FUNCTION.md — Principles for all functions
│   ├── feedback/             — Feedback from all client companies
│   │   └── dayflow/          — DayFlow's feedback
│   └── research/             — Ongoing research
│
├── dayflow/                  — First client company
│   ├── PRODUCT-KNOWLEDGE-SYSTEM.md — DayFlow-specific dependencies
│   ├── adapted-principles/   — Sutra principles adapted for DayFlow
│   └── feedback-to-sutra/    — Incidents and learnings sent to Sutra
│
└── holding/                  — Asawa Inc. level
    ├── decisions/
    └── reviews/
```
