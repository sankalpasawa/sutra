# DayFlow — Organizational Processes

Every idea goes through a formal process. No shortcuts. Every step documented. Every decision logged. Every trade-off recorded.

## The Feature Lifecycle (SDLC)

```
IDEA
  ↓
INTAKE (Problem Statement + Solution Hypothesis)
  ↓
EVALUATION (Business impact, effort, priority score)
  ↓
SPEC (Product spec, design spec, tech spec)
  ↓
REVIEW (Cross-functional review by relevant CXOs)
  ↓
APPROVAL (CEO/Founder decides: build / defer / kill)
  ↓
IMPLEMENTATION (Code, following architecture and design specs)
  ↓
QA (Automated tests + design QA + manual verification)
  ↓
SHIP (Commit, push, deploy)
  ↓
MONITOR (Analytics, user feedback, bug reports)
  ↓
ITERATE (Next cycle)
```

Every stage produces a document. Every document lives in the repo.

---

## Stage 1: INTAKE

**Owner**: CPO (Product Agent)
**Trigger**: Any new idea from founder, user feedback, or agent recommendation
**Output**: `org/features/{feature-slug}/INTAKE.md`

### Template: INTAKE.md
```markdown
# Feature: {name}

## Problem Statement
What problem does this solve? Who has this problem? How do we know?

## Current State
How does the user handle this today? What's broken or missing?

## Proposed Solution
One paragraph. What will we build?

## Success Criteria
How do we know this worked? Specific metrics.

## Source
Where did this idea come from? (founder, user feedback, agent, competitor)

## Date
{YYYY-MM-DD}

## Status
INTAKE → [EVALUATION] → SPEC → REVIEW → APPROVED → BUILDING → QA → SHIPPED
```

---

## Stage 2: EVALUATION

**Owner**: CEO (Strategy Agent) + CGO (Growth Agent)
**Input**: INTAKE.md
**Output**: Updates INTAKE.md with evaluation section, or creates `EVALUATION.md`

### Evaluation Framework (RICE Score)

| Factor | Score | How to calculate |
|--------|-------|-----------------|
| **Reach** | 1-10 | How many users does this affect? (10 = all users, 1 = edge case) |
| **Impact** | 1-10 | How much does it improve their experience? (10 = transformative, 1 = minor) |
| **Confidence** | 1-10 | How sure are we this will work? (10 = validated, 1 = guess) |
| **Effort** | 1-10 | How hard is it to build? (10 = trivial, 1 = massive, INVERTED) |

**Priority Score** = (Reach × Impact × Confidence) / (11 - Effort)

Score > 50: P0 (build now)
Score 20-50: P1 (build soon)
Score 10-20: P2 (build later)
Score < 10: Defer or kill

### Business Questions
- Does this increase retention? (DAU/MAU ratio)
- Does this increase engagement? (sessions per day, time in app)
- Does this reduce churn? (users who stop using the app)
- Does this create a moat? (something competitors can't easily copy)
- Does this align with the cognitive architecture vision?

---

## Stage 3: SPEC

Three specs are created in parallel. Each owned by a different CXO.

### Product Spec (Owner: CPO)
**Output**: `org/features/{feature-slug}/PRODUCT-SPEC.md`

```markdown
# Product Spec: {feature name}

## User Stories
As a [user], I want to [action], so that [benefit].

## Requirements
### Must Have (P0)
- ...
### Should Have (P1)
- ...
### Nice to Have (P2)
- ...

## User Flow
Step-by-step flow from entry point to completion.

## Edge Cases
What happens when: empty state, error, timeout, too many items, etc.

## Metrics
What events to track. What dashboards to create.

## Open Questions
Anything unresolved.
```

### Design Spec (Owner: CDO)
**Output**: `org/features/{feature-slug}/DESIGN-SPEC.md` + mockup HTML in `designs/`

```markdown
# Design Spec: {feature name}

## Visual Design
- Layout (measurements, spacing)
- Colors (which tokens)
- Typography (which scale entries)
- Glass morphism treatment
- Shadows

## States
- Default
- Loading
- Empty
- Error
- Completed
- Compact (if applicable)

## Interactions
- Tap behavior
- Swipe behavior
- Long press
- Animation specs (spring values, duration)

## Accessibility
- Touch targets (minimum 44px)
- Labels for screen readers
- Color contrast ratios

## Mockup
Link to HTML mockup in designs/ folder.
```

### Tech Spec (Owner: CTO)
**Output**: `org/features/{feature-slug}/TECH-SPEC.md`

```markdown
# Tech Spec: {feature name}

## Architecture
Which layer does this touch? (UI, Data, World Context, User Model, AI)

## Files to Create/Modify
- {file path} — {what changes}

## Data Model Changes
- New fields, new tables, migrations needed

## API Changes
- Edge function changes, new endpoints

## Dependencies
- New packages needed
- Existing code that needs refactoring first

## Rendering Rules
How does this data render? (pill, watermark, task, custom)

## Performance Considerations
- Impact on scroll performance
- LLM token usage
- Database query complexity

## Risks
Technical risks and mitigation strategies.
```

---

## Stage 4: REVIEW

**Owner**: All relevant CXOs
**Input**: All three specs
**Output**: `org/features/{feature-slug}/REVIEW.md`

Each CXO reviews the specs from their perspective:

| Reviewer | Checks |
|----------|--------|
| CEO | Does this align with vision? Is the priority right? |
| CDO | Is the design spec complete? Does it match DESIGN.md? |
| CTO | Is the tech spec sound? Does it follow ARCHITECTURE.md? |
| CISO | Any security implications? Data privacy concerns? |
| CQO | What tests are needed? Is it testable? |
| CDaO | What analytics events are needed? |

Review produces: APPROVED / NEEDS CHANGES / DEFERRED / KILLED

---

## Stage 5: APPROVAL

**Owner**: CEO (Founder)
**The founder makes the final call.** Agents recommend. The founder decides.

If APPROVED: status moves to BUILDING.
If NEEDS CHANGES: specs are updated and re-reviewed.
If DEFERRED: logged with reason and revisit date.
If KILLED: logged with reason. Not deleted. We learn from killed ideas.

---

## Stage 6: IMPLEMENTATION

**Owner**: CTO (Engineering Agent)
**Input**: Approved specs
**Output**: Code + commits

### Implementation Rules
1. Read all three specs before writing code
2. Follow ARCHITECTURE.md (five-layer model)
3. Follow DESIGN.md (design system)
4. Follow FEATURE-SPECS.md for component specs
5. One commit per logical change
6. Commit messages reference the feature: `feat({feature-slug}): description`

### During Implementation
- If a spec question arises → log to REVIEW.md, tag the relevant CXO
- If a trade-off must be made → log to `org/decisions/{date}-{topic}.md`
- If scope creeps → stop, update PRODUCT-SPEC.md, get re-approval

---

## Stage 7: QA

**Owner**: CQO (Quality Agent)
**Input**: Implemented code
**Output**: `org/features/{feature-slug}/QA-REPORT.md`

### QA Checklist
1. **Unit tests**: All test cases from TEST-PLAN.md for this feature pass
2. **Design QA**: Run DESIGN-QA-CHECKLIST.md for affected components
3. **Feature tests**: Every user story from PRODUCT-SPEC.md verified
4. **Edge cases**: Every edge case from PRODUCT-SPEC.md tested
5. **Regression**: No existing tests broken
6. **Design token check**: grep for hardcoded values
7. **Performance**: No frame drops, no slow queries

### QA Report Template
```markdown
# QA Report: {feature name}

## Test Results
- Unit tests: {X}/{Y} passing
- Design checks: {X}/{Y} passing
- Feature tests: {pass/fail per story}
- Regression: {pass/fail}

## Issues Found
- {issue 1} — severity, status
- {issue 2} — severity, status

## Verdict
SHIP / FIX AND RETEST / BLOCK
```

---

## Stage 8: SHIP

**Owner**: CTO
**Action**: Commit, push, deploy edge functions if needed
**Output**: Update feature status to SHIPPED, update CHANGELOG.md

---

## Stage 9: MONITOR

**Owner**: CDaO (Data Agent)
**Input**: Analytics events from the shipped feature
**Output**: `org/features/{feature-slug}/MONITOR.md`

- Are users using it?
- What's the adoption rate?
- Any errors in logs?
- User feedback?

---

## Stage 10: ITERATE

**Owner**: CPO
Based on monitoring data, create new INTAKE for improvements or follow-up features.

---

## Folder Structure

```
org/
├── ORG.md                          — Org overview
├── PROCESSES.md                    — This file
├── STANDUP-PROTOCOL.md             — Daily standup procedure
├── agents/                         — CXO agent instructions
│   ├── ceo.md
│   ├── cpo.md
│   ├── cdo.md
│   ├── cto.md
│   ├── ciso.md
│   ├── cdao.md
│   ├── cgo.md
│   ├── cqo.md
│   └── cco.md
├── features/                       — Feature lifecycle docs
│   ├── {feature-slug}/
│   │   ├── INTAKE.md
│   │   ├── EVALUATION.md
│   │   ├── PRODUCT-SPEC.md
│   │   ├── DESIGN-SPEC.md
│   │   ├── TECH-SPEC.md
│   │   ├── REVIEW.md
│   │   └── QA-REPORT.md
│   └── ...
├── standup/                        — Daily standup reports
│   └── YYYY-MM-DD.md
└── decisions/                      — Decision records
    └── YYYY-MM-DD-topic.md
```

---

## Decision Record Template

Every significant decision gets a record:

```markdown
# Decision: {title}
**Date**: {YYYY-MM-DD}
**Decided by**: {founder / agent name}
**Status**: DECIDED / REVISIT

## Context
What prompted this decision?

## Options Considered
1. {option A} — pros, cons
2. {option B} — pros, cons
3. {option C} — pros, cons

## Decision
We chose {option X} because {rationale}.

## Trade-offs
What we gain: ...
What we lose: ...

## Impact
Which departments/features does this affect?
```

---

## How the Founder Interacts

You are the CEO. The org serves you. Here's how you interact:

| You say | What happens |
|---------|-------------|
| "I have an idea: {X}" | CPO creates INTAKE.md, CEO evaluates, specs are created |
| "standup" | All daily agents run, produce cross-department report |
| "strategy" | CEO runs weekly review, produces strategic priorities |
| "ship {feature}" | CTO ships, CQO runs QA, CDaO sets up monitoring |
| "how's {feature}?" | CPO gives status update across all stages |
| "kill {feature}" | Feature logged as KILLED with reason |
| "what should I work on?" | CEO synthesizes all departments, gives #1 priority |

You never have to manage the process. The process manages itself. You set direction. The org executes.
