# Feature Lifecycle (SDLC)

Every idea goes through a formal process. No shortcuts. Every step documented. Every decision logged. Every trade-off recorded.

```
IDEA
  |
  v
Stage 1: INTAKE (Problem Statement + Solution Hypothesis)
  |                                          Gate: CPO approves intake
  v
Stage 2: EVALUATION (RICE scoring, business impact, effort)
  |                                          Gate: Score determines priority
  v
Stage 3: SPEC (Product spec + Design spec + Tech spec)
  |                                          Gate: All three specs complete
  v
Stage 4: REVIEW (Cross-functional review by all departments)
  |                                          Gate: All reviewers approve
  v
Stage 5: APPROVAL (Founder decides: build / defer / kill)
  |                                          Gate: Founder says "build"
  v
Stage 6: IMPLEMENTATION (Code, following specs and architecture)
  |                                          Gate: Code complete, self-reviewed
  v
Stage 7: QA (Automated tests + design QA + manual verification)
  |                                          Gate: QA verdict = SHIP
  v
Stage 8: SHIP (Commit, push, deploy)
  |                                          Gate: Deploy successful
  v
Stage 9: MONITOR (Analytics, user feedback, bug reports)
  |                                          Gate: 7 days of clean data
  v
Stage 10: ITERATE (Next cycle based on learnings)
```

Every stage produces a document. Every document lives in the repo under `org/features/{feature-slug}/`.

---

## Stage 1: INTAKE

**Owner**: CPO (Product Department)
**Trigger**: New idea from founder, user feedback, agent recommendation, competitive analysis
**Duration**: < 1 day
**Output**: `org/features/{feature-slug}/INTAKE.md`

### Template

```markdown
# Feature: {name}
Slug: {feature-slug}
Date: {YYYY-MM-DD}
Source: {founder | user-feedback | agent:{name} | competitor:{name}}

## Problem Statement
What problem does this solve? Who has this problem? How do we know it's real?
Evidence: {user quotes, data, observation}

## Current State
How does the user handle this today? What's broken or missing?

## Proposed Solution
One paragraph. What will we build? Keep it concise.

## Success Criteria
How do we know this worked? Specific, measurable outcomes.
- Metric 1: {name} goes from {baseline} to {target}
- Metric 2: {name} goes from {baseline} to {target}

## Scope Boundaries
What is explicitly OUT of scope for v1?

## Status
[INTAKE] -> EVALUATION -> SPEC -> REVIEW -> APPROVED -> BUILDING -> QA -> SHIPPED
```

### Gate: CPO Review
- Is the problem real? (evidence required)
- Is the solution specific enough to evaluate?
- Are success criteria measurable?
- **Pass**: Move to EVALUATION
- **Fail**: Reject with reason, or request more information

---

## Stage 2: EVALUATION

**Owner**: CPO + CEO (Product + Strategy)
**Input**: INTAKE.md
**Duration**: < 1 day
**Output**: EVALUATION section appended to INTAKE.md

### RICE Scoring Framework

| Factor | Score | How to Calculate |
|--------|-------|-----------------|
| **Reach** | 1-10 | How many users does this affect? (10 = all, 1 = edge case) |
| **Impact** | 1-10 | How much does it improve experience? (10 = transformative, 1 = minor) |
| **Confidence** | 1-10 | How sure are we? (10 = validated with data, 1 = pure guess) |
| **Effort** | 1-10 | How hard to build? (10 = trivial, 1 = massive) NOTE: inverted scale |

**Priority Score** = (Reach x Impact x Confidence) / (11 - Effort)

| Score | Priority | Action |
|-------|----------|--------|
| > 50 | P0 | Build now. Drop other work if needed. |
| 20-50 | P1 | Build this sprint. |
| 10-20 | P2 | Build next sprint. |
| < 10 | P3/Defer | Backlog or kill. |

### Business Questions (must answer all)
- Does this increase retention? (DAU/MAU impact)
- Does this increase engagement? (sessions/day, time-in-app)
- Does this reduce churn? (users who stop using)
- Does this create a moat? (hard for competitors to copy)
- Does this align with the cognitive architecture vision?

### Gate: Priority Assignment
- RICE score calculated and logged
- Priority assigned (P0/P1/P2/P3)
- **P0**: Skip to SPEC immediately, fast-track all gates
- **P1**: Queue for next sprint's spec phase
- **P2/P3**: Add to backlog, review at weekly planning
- **Kill**: Log reason in INTAKE.md, move to `org/features/killed/`

---

## Stage 3: SPEC

**Owner**: CPO + CDO + CTO (Product + Design + Engineering) — in parallel
**Input**: Evaluated INTAKE.md
**Duration**: 1-2 days for P0, up to 1 week for P1
**Output**: Three spec documents

### 3A: Product Spec (Owner: CPO)
**Output**: `org/features/{feature-slug}/PRODUCT-SPEC.md`

```markdown
# Product Spec: {feature name}
Date: {YYYY-MM-DD}
Author: CPO
Status: DRAFT | REVIEW | APPROVED

## User Stories
As a [user], I want to [action], so that [benefit].
(One story per distinct user need)

## Requirements
### Must Have (P0)
- {requirement} — acceptance criteria: {how to verify}
### Should Have (P1)
- {requirement} — acceptance criteria: {how to verify}
### Nice to Have (P2)
- {requirement} — acceptance criteria: {how to verify}

## User Flow
1. User opens {screen}
2. User taps {element}
3. System shows {response}
4. User completes {action}
5. System confirms {outcome}

## Edge Cases
| Scenario | Expected Behavior |
|----------|------------------|
| Empty state (no data) | {behavior} |
| Error (network) | {behavior} |
| Error (validation) | {behavior} |
| Timeout | {behavior} |
| Too many items | {behavior} |
| Concurrent edits | {behavior} |

## Analytics Events
| Event Name | Trigger | Properties |
|-----------|---------|-----------|
| {event} | {when} | {what data} |

## Open Questions
- {anything unresolved — must be resolved before REVIEW gate}
```

### 3B: Design Spec (Owner: CDO)
**Output**: `org/features/{feature-slug}/DESIGN-SPEC.md`

```markdown
# Design Spec: {feature name}
Date: {YYYY-MM-DD}
Author: CDO
Status: DRAFT | REVIEW | APPROVED

## Visual Design
- Layout: {measurements, spacing, alignment — all on 4px grid}
- Colors: {token names from DESIGN.md — never hex values}
- Typography: {scale entries from DESIGN.md}
- Glass morphism: {blur, opacity, border treatment}
- Shadows: {elevation level from theme}

## Component Breakdown
| Component | Existing/New | Spec Reference |
|-----------|-------------|----------------|
| {component} | Existing | FEATURE-SPECS.md#{section} |
| {component} | New | See below |

## States
| State | Description | Visual Treatment |
|-------|------------|-----------------|
| Default | Normal view | {description} |
| Loading | Data fetching | Skeleton screen |
| Empty | No data | {empty state design + copy} |
| Error | Operation failed | {error treatment + copy} |
| Completed | Action done | {success treatment} |
| Compact | Reduced size (if applicable) | {compact layout} |

## Interactions
| Gesture | Trigger | Animation | Duration |
|---------|---------|-----------|----------|
| Tap | {element} | {response} | {ms or spring config} |
| Swipe right | {element} | {response} | {spring config} |
| Long press | {element} | {response} | {delay + response} |
| Pull down | {screen} | {response} | {spring config} |

## Accessibility
- Touch targets: minimum 44x44px
- Labels: {screen reader labels for all interactive elements}
- Contrast: {ratios for text/background combinations}
- Motion: {reduced motion alternative}

## Mockup
Link: {designs/{feature-slug}.html or Figma link}
```

### 3C: Tech Spec (Owner: CTO)
**Output**: `org/features/{feature-slug}/TECH-SPEC.md`

```markdown
# Tech Spec: {feature name}
Date: {YYYY-MM-DD}
Author: CTO
Status: DRAFT | REVIEW | APPROVED

## Architecture Layer
{Which of the five layers does this touch?}
- [ ] UI (skin)
- [ ] Data (spine)
- [ ] World Context (senses)
- [ ] User Model (memory)
- [ ] AI (brain)

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| {path} | Create | {description} |
| {path} | Modify | {what changes} |

## Data Model Changes
| Table | Column | Type | Migration |
|-------|--------|------|-----------|
| {table} | {column} | {type} | {SQL migration} |

## API Changes
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| {path} | {GET/POST} | {required/public} | {what it does} |

## Dependencies
- New packages: {package@version — justification}
- Existing code requiring refactor: {file — what needs to change first}

## Rendering Rules
How does this data render? {pill | watermark | task | custom}

## Performance Considerations
- Scroll impact: {none | minor | needs optimization}
- LLM token usage: {estimate}
- Database query complexity: {simple | needs index | complex join}

## Risks
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| {risk} | {H/M/L} | {H/M/L} | {strategy} |

## Estimated Effort
{X hours/days} — {trivial | moderate | complex | architectural}
```

### Gate: Spec Completeness
- All three specs complete (no blank sections)
- Open questions in Product Spec resolved
- Design spec references only design tokens (no hardcoded values)
- Tech spec has effort estimate
- **Pass**: Move to REVIEW
- **Fail**: Return to spec authors with specific gaps

---

## Stage 4: REVIEW

**Owner**: All relevant departments
**Input**: All three specs
**Duration**: < 1 day for P0, 2-3 days for P1
**Output**: `org/features/{feature-slug}/REVIEW.md`

### Review Matrix

| Reviewer | Department | Checks |
|----------|-----------|--------|
| CPO | Product | User stories complete? Edge cases covered? |
| CDO | Design | Matches design system? All states designed? Accessible? |
| CTO | Engineering | Architecture sound? Effort accurate? Risks identified? |
| CISO | Security | Data privacy? Auth requirements? New attack surface? |
| CQO | Quality | Testable? Test cases obvious? Edge cases verifiable? |
| CDaO | Data | Analytics events defined? Dashboards needed? |
| CCO | Content | Copy written? Tone correct? Accessibility labels? |

### Review Template

```markdown
# Review: {feature name}
Date: {YYYY-MM-DD}

## Reviewer Sign-offs
| Reviewer | Verdict | Notes |
|----------|---------|-------|
| CPO | APPROVE / NEEDS CHANGES | {notes} |
| CDO | APPROVE / NEEDS CHANGES | {notes} |
| CTO | APPROVE / NEEDS CHANGES | {notes} |
| CISO | APPROVE / NEEDS CHANGES | {notes} |
| CQO | APPROVE / NEEDS CHANGES | {notes} |
| CDaO | APPROVE / NEEDS CHANGES | {notes} |
| CCO | APPROVE / NEEDS CHANGES | {notes} |

## Overall Verdict
{APPROVED | NEEDS CHANGES | DEFERRED | KILLED}

## Changes Required (if NEEDS CHANGES)
1. {change} — owner: {department} — deadline: {date}

## Concerns Raised
- {concern} — {how addressed or accepted as risk}
```

### Gate: Review Approval
- All mandatory reviewers (CPO, CDO, CTO) have signed off
- No unresolved NEEDS CHANGES
- Security has no blocking concerns
- **Pass**: Move to APPROVAL
- **Fail**: Return to SPEC stage with change list

---

## Stage 5: APPROVAL

**Owner**: Founder (CEO)
**Input**: Review-approved specs
**Duration**: < 1 day
**The founder makes the final call.** Agents recommend. The founder decides.

### Outcomes
| Decision | What Happens |
|----------|-------------|
| **APPROVED** | Status -> BUILDING. Engineering begins implementation. |
| **NEEDS CHANGES** | Specs updated per feedback, re-enter REVIEW. |
| **DEFERRED** | Logged with reason and revisit date. Not deleted. |
| **KILLED** | Logged with reason in INTAKE.md. Not deleted. We learn from killed ideas. |

### Gate: Founder Decision
- Founder has reviewed all specs
- Decision recorded in INTAKE.md status field
- If APPROVED: Engineering notified with target sprint

---

## Stage 6: IMPLEMENTATION

**Owner**: CTO (Engineering Department)
**Input**: Approved specs (all three)
**Duration**: Per effort estimate in Tech Spec
**Output**: Working code + commits

### Implementation Rules
1. Read ALL THREE specs before writing any code
2. Follow ARCHITECTURE.md (five-layer model)
3. Follow DESIGN.md (design system tokens)
4. Follow FEATURE-SPECS.md for component measurements
5. One commit per logical change
6. Commit messages: `feat({feature-slug}): description`

### During Implementation
- Spec question arises -> comment in REVIEW.md, tag relevant department
- Trade-off needed -> log to `org/decisions/{date}-{topic}.md`
- Scope creep detected -> STOP, update PRODUCT-SPEC.md, get re-approval
- Blocker found -> notify Operations for resolution

### Gate: Code Complete
- All P0 requirements from Product Spec implemented
- Design spec followed (tokens, measurements, states)
- Self-reviewed against Tech Spec
- No TypeScript errors
- Existing tests still pass
- **Pass**: Notify Quality for QA
- **Fail**: Continue implementation

---

## Stage 7: QA

**Owner**: CQO (Quality Department)
**Input**: Code-complete implementation
**Duration**: < 1 day for small features, 2-3 days for complex
**Output**: `org/features/{feature-slug}/QA-REPORT.md`

### QA Checklist
1. **Feature tests**: Every user story from PRODUCT-SPEC.md verified
2. **Edge cases**: Every edge case from PRODUCT-SPEC.md tested
3. **Design QA**: Visual compliance with DESIGN-SPEC.md
4. **Design tokens**: Grep for hardcoded values (zero tolerance)
5. **Unit tests**: New test cases written and passing
6. **Regression**: All existing tests still pass
7. **Performance**: No frame drops, no slow queries, no memory leaks
8. **Accessibility**: Touch targets, labels, contrast verified
9. **Content**: Copy matches approved strings from Content department

### QA Report Template

```markdown
# QA Report: {feature name}
Date: {YYYY-MM-DD}
Tester: CQO Agent

## Test Results
| Category | Pass | Fail | Total |
|----------|------|------|-------|
| User stories | {n} | {n} | {n} |
| Edge cases | {n} | {n} | {n} |
| Design QA | {n} | {n} | {n} |
| Regression | {n} | {n} | {n} |
| Performance | {n} | {n} | {n} |

## Issues Found
| # | Description | Severity | Owner | Status |
|---|------------|----------|-------|--------|
| 1 | {desc} | P{0-3} | {dept} | Open |

## Design Token Compliance
- Hardcoded colors: {count} (must be 0)
- Hardcoded spacing: {count} (must be 0)
- Hardcoded fonts: {count} (must be 0)

## Verdict
{SHIP | FIX AND RETEST | BLOCK}

## Notes
{observations, recommendations, caveats}
```

### Gate: QA Verdict
- **SHIP**: All tests pass, zero P0/P1 issues, design compliant -> move to SHIP
- **FIX AND RETEST**: P1/P2 issues found -> Engineering fixes, QA re-runs
- **BLOCK**: P0 issues found or fundamental problems -> back to IMPLEMENTATION

---

## Stage 8: SHIP

**Owner**: CTO (Engineering Department)
**Input**: QA-approved code
**Duration**: < 1 hour
**Output**: Deployed code, updated changelog

### Ship Checklist
1. All commits squashed or organized logically
2. Commit messages follow convention
3. CHANGELOG.md updated with user-facing changes
4. Edge functions deployed (if applicable)
5. Feature flag enabled (if applicable)
6. Status updated to SHIPPED in INTAKE.md

### Gate: Deploy Success
- Code pushed to main branch
- Build succeeds
- Edge functions deployed (if any)
- No deployment errors
- **Pass**: Move to MONITOR
- **Fail**: Rollback, investigate, fix

---

## Stage 9: MONITOR

**Owner**: CDaO (Data Department)
**Input**: Shipped feature + analytics events
**Duration**: 7 days minimum
**Output**: `org/features/{feature-slug}/MONITOR.md`

### Monitoring Checklist
- Are analytics events firing correctly?
- Are users using the feature? (adoption rate)
- Any errors in logs? (error rate)
- Performance in production? (latency, crashes)
- User feedback? (app store reviews, support)

### Monitor Report Template

```markdown
# Monitor Report: {feature name}
Period: {start date} to {end date}

## Adoption
- Users who used feature: {count} ({percent} of active users)
- Usage frequency: {times per user per day}
- Trend: {increasing | stable | declining}

## Performance
- Error rate: {percent}
- Latency (p50/p95): {ms} / {ms}
- Crashes attributed: {count}

## User Feedback
- Positive: {summary}
- Negative: {summary}
- Requests: {summary}

## Success Criteria Check
| Criteria (from INTAKE) | Target | Actual | Status |
|----------------------|--------|--------|--------|
| {metric} | {target} | {actual} | {pass/fail} |

## Recommendation
{Keep as-is | Iterate (see Stage 10) | Deprecate}
```

### Gate: Clean Monitoring
- 7 days of data collected
- Error rate < 1%
- No P0 bugs reported
- Success criteria evaluated
- **Pass**: Move to ITERATE (or close if fully successful)
- **Fail**: Create P0 bug tickets, re-enter IMPLEMENTATION

---

## Stage 10: ITERATE

**Owner**: CPO (Product Department)
**Input**: Monitor report + user feedback
**Duration**: Ongoing
**Output**: New INTAKE.md(s) for improvements

### Iteration Triggers
- Success criteria not met -> investigate and propose fix
- User feedback suggests improvement -> new INTAKE
- Usage data shows unexpected pattern -> analyze and decide
- Related feature requested -> new INTAKE referencing this feature

The cycle repeats. Every iteration goes through the full lifecycle again, but may fast-track through stages if the scope is small.

---

## Stage Failure Recovery

| Stage | If It Fails | Recovery |
|-------|------------|----------|
| INTAKE | Problem not validated | Gather more evidence or kill |
| EVALUATION | Score too low | Defer to backlog or kill |
| SPEC | Specs incomplete | Return to spec authors with gaps |
| REVIEW | Reviewers reject | Update specs, re-review |
| APPROVAL | Founder says no | Defer or kill with reason |
| IMPLEMENTATION | Can't build as specced | Update tech spec, notify Product |
| QA | Tests fail | Fix bugs, retest |
| SHIP | Deploy fails | Rollback, investigate, fix |
| MONITOR | Bad metrics | Create P0 fix tickets |
| ITERATE | No clear improvement | Gather more data or accept |

---

## Depth Integration

The Adaptive Protocol Engine (PROTO-000) depth assessment determines how much of the lifecycle runs for a given feature.

| Depth | Stages Applied | Documentation |
|-------|---------------|---------------|
| 1 (Surface) | INTAKE (1-line) -> IMPLEMENTATION -> SHIP | Minimal: commit message only |
| 2 (Considered) | INTAKE -> EVALUATION (quick RICE) -> IMPLEMENTATION -> QA (smoke test) -> SHIP | One-page feature doc |
| 3 (Thorough) | Full 10-stage lifecycle, abbreviated specs | All templates, sections can be brief |
| 4 (Rigorous) | Full 10-stage lifecycle, complete specs | All templates filled completely |
| 5 (Exhaustive) | Full lifecycle + cross-functional review + ADR + post-ship retro | Full documentation, decision records |

**Rule**: Stages are never invented — they are scaled. Depth 1-2 compresses the pipeline; Depth 3+ runs it fully. The depth assessment happens once at INTAKE and governs the entire lifecycle for that feature.

---

*This lifecycle applies to ALL features regardless of size. For tiny features (< 2 hours), stages can be abbreviated but not skipped. Every stage must produce at least a one-line entry in the feature's documentation.*
