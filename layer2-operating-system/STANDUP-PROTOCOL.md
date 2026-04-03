# Daily Standup Protocol

## How to Run

Type `/standup` in Claude Code. This triggers the following:

## Standup Sequence

### Phase 1: Data Collection (parallel agents)

Launch these agents simultaneously:

1. **CQO (Quality)** — runs first because it produces data others need
   - Grep for hardcoded hex colors
   - Count implemented vs planned tests from TEST-PLAN.md
   - Check DESIGN-QA-CHECKLIST.md compliance
   - Output: test coverage, regressions, design token violations

2. **CDO (Design)** — checks visual quality
   - Read DESIGN.md, compare against theme.ts values
   - Read recent commits for style changes
   - Check FEATURE-SPECS.md for any spec without implementation
   - Output: pixel mismatches, design debt

3. **CTO (Engineering)** — checks code health
   - File size analysis (any .tsx > 500 lines?)
   - Import cycle detection
   - Architecture rule check (rendering rules, layer separation)
   - Git diff: what changed since last standup?
   - Output: tech debt score, refactoring priorities

4. **CDaO (Data)** — checks analytics readiness
   - Is PostHog/analytics integrated?
   - What events are tracked vs should be tracked?
   - Output: analytics coverage

### Phase 2: Synthesis (CEO agent)

After Phase 1 agents complete:

5. **CEO (Strategy)** — reads all Phase 1 outputs + TODO.md + PLAN.md
   - Synthesizes into a single prioritized action list
   - Checks cross-department balance
   - Identifies the ONE most important thing for today
   - Output: daily priority list + department health table

### Phase 3: Report

Write the combined report to `org/standup/{YYYY-MM-DD}.md`

## Report Template

```markdown
# Standup — {date}

## Today's #1 Priority
{The single most important thing to work on}

## Department Reports

### Quality (CQO)
- Tests: {X}/{Y} implemented ({Z}% coverage)
- Design tokens: {N} violations found
- Regressions: {list or "none"}

### Design (CDO)
- Design debt: {score}/10
- Mismatches: {list or "all clear"}
- New specs needed: {list or "none"}

### Engineering (CTO)
- Tech debt: {score}/10
- Large files: {list of files > 500 lines}
- Architecture: {violations or "clean"}

### Data (CDaO)
- Analytics: {integrated/not integrated}
- Events tracked: {X}/{Y recommended}

### Product (CPO)
- Features in progress: {count}
- Blocked: {list or "none"}
- User asks pending: {count}

## Action Items (priority order)
1. {action} — {department} — {effort estimate}
2. {action} — {department} — {effort estimate}
3. {action} — {department} — {effort estimate}

## Risks
- {risk if any}

## Decisions Needed
- {any decision requiring founder input}
```

## Weekly Additions (Monday standup)

On Mondays, also run:
- **CISO (Security)** — vulnerability scan, compliance check
- **CGO (Growth)** — onboarding review, retention analysis
- **CEO Strategy Review** — weekly retro, next week planning

## How Agents Persist State

Each agent reads:
- The codebase (current state of truth)
- Previous standup reports (for trend analysis)
- org/decisions/ (for context on past decisions)

Each agent writes:
- Their section of the standup report
- Any new decision to org/decisions/ (if they made one)
- Updated tasks to TODO.md (if they found new work)

## Implementation

When `/standup` is invoked:

```
1. Read org/agents/cqo.md — run Quality check
2. Read org/agents/cdo.md — run Design check
3. Read org/agents/cto.md — run Engineering check
4. Read org/agents/cdao.md — run Data check
   (all four run as parallel agents)
5. Collect outputs
6. Read org/agents/ceo.md — synthesize
7. Write report to org/standup/{date}.md
8. Print summary to user
```
