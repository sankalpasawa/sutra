# Daily Standup Protocol

## Overview

> **NOTE:** This file references `org/standup/` and `org/decisions/` directories that do not exist in the Sutra OS template. Client companies using this protocol must create these directories in their own repo (e.g., `org/standup/`, `org/decisions/`).

The daily standup is the company's heartbeat. It runs at the start of every session (conceptually 7 AM). It produces a cross-practice health report, identifies the day's top priority, and routes action items to the right practices.

## When It Runs
- Triggered by: `/standup` command, session start, or "standup" keyword
- Frequency: Once per day (skip if already run today — check `org/standup/{date}.md`)
- Duration: 3-5 minutes total

---

## Phase 1: Data Collection (Parallel Agents)

Launch these four agents simultaneously. They run independently and do not depend on each other.

### Agent 1: Quality (CQO)
**Reads**: source code, TEST-PLAN.md, DESIGN-QA-CHECKLIST.md, theme.ts
**Checks**:
1. Grep `src/` for hardcoded hex colors (pattern: `/#[0-9a-fA-F]{3,8}/` outside theme.ts)
2. Grep for hardcoded spacing values outside theme.ts
3. Count implemented vs planned tests from TEST-PLAN.md
4. Run existing test suite, report pass/fail counts
5. Check for `test.skip` or `xit` (skipped tests)
6. Review recent commits for potential regressions
**Output format**:
```
[QUALITY]
Tests: {pass}/{total} passing ({coverage}% coverage)
Skipped tests: {count}
Design token violations: {count} ({details if > 0})
Regressions detected: {list or "none"}
Action items: {list or "none"}
```

### Agent 2: Design (CDO)
**Reads**: DESIGN.md, FEATURE-SPECS.md, theme.ts, recent git diff for UI changes
**Checks**:
1. Compare theme.ts values against DESIGN.md specifications
2. Check recent commits for UI/style changes
3. Verify FEATURE-SPECS.md covers all implemented components
4. Check for components missing design specs
5. Review accessibility: touch targets, contrast ratios
**Output format**:
```
[DESIGN]
Design debt score: {1-10}/10
Pixel mismatches: {list or "all clear"}
Specs missing: {components without specs}
Accessibility issues: {list or "passing"}
Action items: {list or "none"}
```

### Agent 3: Engineering (CTO)
**Reads**: source code, ARCHITECTURE.md, git log, package.json
**Checks**:
1. File size analysis: any `.tsx`/`.ts` files > 400 lines
2. Import cycle detection (circular dependencies)
3. Architecture rule compliance (rendering rules, layer separation)
4. Git diff since last standup (what changed?)
5. TypeScript strict mode compliance (`any` type usage)
6. Dependency health (`npm audit` summary)
**Output format**:
```
[ENGINEERING]
Tech debt score: {1-10}/10
Large files (>400 lines): {list or "none"}
Circular imports: {count}
Architecture violations: {list or "clean"}
Recent changes: {summary of git diff}
Action items: {list or "none"}
```

### Agent 4: Data (CDaO)
**Reads**: source code for analytics calls, PostHog configuration
**Checks**:
1. Is analytics SDK integrated?
2. What events are currently tracked vs should be tracked?
3. Any new features shipped without analytics events?
4. Data pipeline health (if applicable)
**Output format**:
```
[DATA]
Analytics status: {integrated/not integrated}
Events tracked: {count}/{recommended count}
Untracked features: {list or "all covered"}
Action items: {list or "none"}
```

---

## Phase 2: Extended Checks (Weekly Only — Monday)

On Mondays, also launch these agents in parallel with Phase 1:

### Agent 5: Security (CISO)
**Checks**:
1. `npm audit` for vulnerabilities
2. Grep for secrets/credentials in source
3. RLS policy review
4. JWT validation coverage
**Output**: Security health summary

### Agent 6: Growth (CGO)
**Checks**:
1. Onboarding flow completeness
2. Retention hook implementation status
3. App store readiness checklist
4. Push notification system status
**Output**: Growth readiness summary

### Agent 7: Content (CCO)
**Checks**:
1. Documentation freshness (files not updated in > 2 weeks)
2. Changelog currency
3. In-app copy audit (empty states, error messages)
**Output**: Content health summary

---

## Phase 3: Synthesis (CEO Agent)

After all Phase 1 agents complete (and Phase 2 on Mondays):

### CEO Agent Process
1. Read all agent outputs from Phase 1 (and Phase 2 if Monday)
2. Read TODO.md for current task list
3. Read PLAN.md for product direction
4. Read previous standup for trend analysis
5. Synthesize into:
   a. **Today's #1 Priority** — the single most important thing
   b. **Practice health table** — red/yellow/green per practice
   c. **Prioritized action items** — numbered list with practice assignments
   d. **Risks** — anything that could derail progress
   e. **Decisions needed** — anything requiring founder input

### Priority Selection Logic
1. P0 bugs or security issues -> always #1
2. Blocked cross-practice items -> #2
3. Current sprint P0 features -> #3
4. Tech/design debt above threshold -> #4
5. Regular sprint work -> #5

---

## Phase 4: Report Generation

Write the combined report to `org/standup/{YYYY-MM-DD}.md`.

### Report Template

```markdown
# Standup — {YYYY-MM-DD}

## Today's #1 Priority
{The single most important thing to work on today}

## Practice Health
| Practice | Status | Score | Key Issue |
|-----------|--------|-------|-----------|
| Quality | {green/yellow/red} | {score} | {one-line summary} |
| Design | {green/yellow/red} | {score} | {one-line summary} |
| Engineering | {green/yellow/red} | {score} | {one-line summary} |
| Data | {green/yellow/red} | {score} | {one-line summary} |
| Product | {green/yellow/red} | {score} | {one-line summary} |
{Add Security, Growth, Content rows on Mondays}

## Practice Reports

### Quality (CQO)
{Full output from Agent 1}

### Design (CDO)
{Full output from Agent 2}

### Engineering (CTO)
{Full output from Agent 3}

### Data (CDaO)
{Full output from Agent 4}

### Product (CPO)
- Features in progress: {count with names}
- Blocked: {list or "none"}
- User asks pending: {count}

## Action Items (priority order)
| # | Action | Practice | Effort | Priority |
|---|--------|-----------|--------|----------|
| 1 | {action} | {dept} | {estimate} | P{0-3} |
| 2 | {action} | {dept} | {estimate} | P{0-3} |
| 3 | {action} | {dept} | {estimate} | P{0-3} |

## Risks
- {risk and potential impact}

## Decisions Needed (Founder Input)
- {decision needed with context and options}

## Trend (vs yesterday)
- Tests: {up/down/stable} ({delta})
- Tech debt: {up/down/stable} ({delta})
- Design compliance: {up/down/stable} ({delta})
```

---

## Phase 5: Action Item Routing

After report is written, route action items to practices:

1. Read each action item from the report
2. Determine owning practice
3. Check `org/ROUTING.md` for any cross-practice routing needed
4. File action items into practice awareness (mention in next relevant context)
5. Track completion in next standup

---

## Implementation Notes

### Running Parallel Agents
```
1. Spawn Agent 1 (CQO) — reads org/practices/quality/PRACTICE.md for instructions
2. Spawn Agent 2 (CDO) — reads org/practices/design/PRACTICE.md for instructions
3. Spawn Agent 3 (CTO) — reads org/practices/engineering/PRACTICE.md for instructions
4. Spawn Agent 4 (CDaO) — reads org/practices/data/PRACTICE.md for instructions
   (All four run in parallel as sub-agents)
5. Collect all outputs
6. Run CEO synthesis
7. Write report to org/standup/{date}.md
8. Print summary to user
```

### State Persistence
- Each agent reads the codebase (current state of truth)
- Previous standup reports provide trend data
- `org/decisions/` provides context on past decisions
- No agent maintains state between sessions — the codebase IS the state

Each agent writes:
- Their section of the standup report
- Any new decision to `org/decisions/` (if they made one)
- Updated tasks to TODO.md (if they found new work)

### Skipping Conditions
- If `org/standup/{today's date}.md` already exists, skip unless forced
- User can force re-run with "standup --force" or "re-run standup"
