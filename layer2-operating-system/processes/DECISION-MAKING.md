# Decision-Making Protocol

## Overview
Every significant decision at DayFlow is made deliberately, documented, and reversible where possible. This protocol defines who can decide what, how decisions are made, and how they are recorded.

---

## Decision Categories

### Category 1: Autonomous Agent Decisions
**No approval needed.** Agents decide within their domain and execute.

| Department | Can Decide Autonomously |
|-----------|----------------------|
| Product | Feature intake, RICE scoring, backlog grooming, user asks logging |
| Design | Token values, component specs, QA verdicts, accessibility fixes |
| Engineering | Code style, refactoring approach, minor library choices, bug fixes, performance optimizations |
| Data | Event schema design, dashboard creation, metric definitions |
| Security | Vulnerability classification, dependency approval, deploy blocks for critical issues |
| Quality | Bug severity, QA verdicts (SHIP/FIX/BLOCK), test strategy |
| Growth | Notification copy iterations, ASO keyword updates, experiment design |
| Operations | Meeting scheduling, blocker routing, process documentation |
| Content | Microcopy writing, error message phrasing, doc updates, terminology standardization |

**Rule**: If the decision is within your domain, easily reversible, and doesn't affect other departments, just do it.

### Category 2: Cross-Department Decisions
**Needs coordination.** Multiple departments affected. Operations facilitates.

Examples:
- Feature prioritization changes (Product + Engineering + Design)
- New component that requires design + engineering + content
- Analytics implementation (Data + Engineering)
- Onboarding redesign (Growth + Design + Product + Content)

**Process**:
1. Initiating department proposes decision
2. Operations identifies affected departments
3. Each department provides input (constraints, concerns, estimates)
4. If consensus: decision is made, logged, and executed
5. If disagreement: escalate to Founder

### Category 3: Founder Decisions
**Founder must approve.** Strategic, high-impact, or taste-sensitive.

Always requires Founder:
- Product vision and strategy changes
- Feature kills or major deprioritizations
- Architecture changes (adding new layers, changing patterns)
- Design aesthetic direction changes
- New acquisition channels or monetization strategy
- Privacy policy or compliance commitments
- Organizational structure changes
- Brand-level decisions (voice, visual identity)
- Scope expansions beyond original spec
- Any decision an agent is uncertain about

**Process**:
1. Agent prepares decision brief (see template below)
2. Present options with recommendation
3. Founder decides
4. Decision logged to `org/decisions/`

---

## Decision-Making Framework

### For Any Non-Trivial Decision

1. **Define the decision**: What exactly are we deciding?
2. **Gather context**: What do we know? What don't we know?
3. **Generate options**: At least 2, ideally 3 options
4. **Evaluate trade-offs**: What do we gain/lose with each option?
5. **Make the call**: Choose and commit
6. **Document**: Log the decision with rationale
7. **Communicate**: Notify affected departments

### Decision Principles
1. **Reversible > irreversible**: Prefer decisions that can be undone. For reversible decisions, decide fast. For irreversible decisions, decide carefully.
2. **Data > opinion**: When data exists, it wins. When it doesn't, state your confidence level.
3. **User > org**: When in doubt, choose what's best for the user.
4. **Ship > perfect**: A good decision now is better than a perfect decision next week.
5. **Document > remember**: Write it down. Memory is unreliable.
6. **Disagree and commit**: Once decided, everyone executes. Revisit at the next weekly planning if needed.

---

## Decision Record Template

Every significant decision gets logged to `org/decisions/{YYYY-MM-DD}-{slug}.md`:

```markdown
# Decision: {title}

**Date**: {YYYY-MM-DD}
**Category**: Autonomous / Cross-Department / Founder
**Decided by**: {agent name or "Founder"}
**Status**: DECIDED | REVISIT on {date} | REVERSED

## Context
What prompted this decision? What's the background?

## Problem Statement
What specific question are we answering?

## Options Considered

### Option A: {name}
- Description: {what this means}
- Pros: {benefits}
- Cons: {drawbacks}
- Effort: {estimate}
- Risk: {H/M/L}

### Option B: {name}
- Description: {what this means}
- Pros: {benefits}
- Cons: {drawbacks}
- Effort: {estimate}
- Risk: {H/M/L}

### Option C: {name} (if applicable)
- Description: {what this means}
- Pros: {benefits}
- Cons: {drawbacks}
- Effort: {estimate}
- Risk: {H/M/L}

## Decision
We chose **Option {X}** because {rationale}.

## Trade-offs Accepted
- We gain: {benefits}
- We lose: {costs}
- We accept risk of: {risks}

## Impact
- Departments affected: {list}
- Files affected: {list if applicable}
- Timeline impact: {description}

## Reversibility
{How easily can this be undone? What would trigger a reversal?}

## Follow-up Actions
| Action | Owner | Deadline |
|--------|-------|---------|
| {action} | {dept} | {date} |
```

---

## Escalation Protocol

### When to Escalate

**Agent to Operations (COO)**:
- Two departments disagree on priority or approach
- A blocker affects multiple departments
- Process failure (something fell through the cracks)
- Resource conflict (two departments need same resource)

**Agent/Operations to Founder**:
- Strategic direction question
- Taste/aesthetic judgment needed
- High-risk decision (irreversible, high impact)
- Budget or resource allocation conflict
- Any Category 3 decision
- Agent is genuinely uncertain (confidence < 50%)

### Escalation Format
When escalating, provide:
1. **What**: One sentence describing the decision needed
2. **Why now**: Why this can't wait
3. **Options**: 2-3 options with trade-offs
4. **Recommendation**: What the agent recommends and why
5. **Impact of delay**: What happens if we don't decide today

---

## Decision Review

### At Weekly Planning
- Review all decisions made this week
- Check: are the outcomes matching expectations?
- Any decisions to revisit or reverse?

### Monthly
- Review all decisions from the past month
- Identify patterns (too many escalations? too slow? wrong calls?)
- Update decision-making guidelines if needed

### Decision Metrics
| Metric | Target | Tracking |
|--------|--------|---------|
| Time to decide (Category 1) | < 1 hour | Audit quarterly |
| Time to decide (Category 2) | < 24 hours | Weekly review |
| Time to decide (Category 3) | < 48 hours | Weekly review |
| Decision reversal rate | < 10% | Monthly review |
| Decisions documented | 100% of Category 2+3 | Weekly review |

---

## Anti-Patterns to Avoid

1. **Decision paralysis**: Spending more time deciding than the decision is worth. If effort to decide > effort to reverse, just pick one.
2. **Design by committee**: Not every department needs to weigh in on every decision. Route to relevant departments only.
3. **Undocumented decisions**: If it's not in `org/decisions/`, it didn't happen. Future agents won't know why we chose what we chose.
4. **Revisiting settled decisions**: Once decided and committed, don't re-open unless new data surfaces. Revisit at weekly planning, not mid-sprint.
5. **Escalation avoidance**: If you're uncertain, escalate. A delayed decision is worse than admitting uncertainty.
6. **Band-aid decisions**: Don't fix symptoms. Identify root causes. Especially for P0/P1 incidents.
