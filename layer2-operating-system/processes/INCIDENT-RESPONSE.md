# Incident Response Protocol

## Overview
When something breaks, we respond systematically. Every incident is classified, assigned, tracked, and post-mortemed. Speed matters, but so does thoroughness — a rushed fix that causes a second incident is worse than a proper fix that takes an hour longer.

---

## Severity Levels

### P0 — Critical
**Definition**: App crashes, data loss, security breach, or complete feature failure affecting all users.
**Examples**:
- App crashes on launch
- User data deleted or corrupted
- Authentication bypass discovered
- Database down or unreachable
- All activities disappearing from view

**Response**:
- **Response time**: Immediate (< 15 minutes)
- **Who is notified**: CTO, CISO (if security), CPO, Founder
- **Action**: Drop all current work. All Engineering resources on this.
- **Deploy block**: No other code ships until P0 is resolved
- **Communication**: Founder notified immediately with impact assessment

### P1 — Major Bug
**Definition**: Core feature broken or severely degraded. Users can work around it but experience is significantly impaired.
**Examples**:
- Creating activities fails intermittently
- Swipe gestures not responding
- Data not syncing between sessions
- Wrong data displayed (times, dates, categories)
- Performance degraded (> 5 second load times)

**Response**:
- **Response time**: < 2 hours
- **Who is notified**: CTO, CPO
- **Action**: Prioritize above all P1 sprint work. Fix within current day.
- **Deploy block**: None, but fix should ship same day
- **Communication**: Logged in standup report

### P2 — Minor Bug
**Definition**: Feature works but has issues. Workaround exists. User experience degraded but not broken.
**Examples**:
- Styling glitch on one screen
- Animation stuttering occasionally
- Edge case not handled (but doesn't crash)
- Non-critical data display issue
- Slow but functional performance

**Response**:
- **Response time**: < 24 hours (acknowledged)
- **Who is notified**: CTO
- **Action**: Fix within current sprint
- **Deploy block**: None
- **Communication**: Tracked in TODO.md

### P3 — Cosmetic / Minor
**Definition**: Polish issues. Users unlikely to notice or care. No functional impact.
**Examples**:
- 1px alignment issue
- Color slightly off from design spec
- Unnecessary console.log in production
- Minor copy typo
- Animation timing feels slightly off

**Response**:
- **Response time**: Acknowledged within 48 hours
- **Who is notified**: Relevant department head
- **Action**: Fix when convenient or batch with other P3s
- **Deploy block**: None
- **Communication**: Tracked in TODO.md with [P3] tag

---

## Incident Response Flow

### Step 1: Detection
Incident discovered through:
- QA testing (Quality department)
- User feedback / app store review
- Analytics anomaly (Data department)
- Automated monitoring / error tracking
- Manual testing during standup
- Founder report

### Step 2: Classification
The discovering department classifies severity:
1. What is broken? (describe the symptom)
2. Who is affected? (all users, some users, edge case)
3. Is there a workaround? (yes = P2+, no = P0/P1)
4. Is data at risk? (yes = P0)
5. Assign severity: P0 / P1 / P2 / P3

### Step 3: Notification
Follow the notification matrix:

| Severity | Engineering | Product | Security | Design | Operations | Founder |
|----------|------------|---------|----------|--------|-----------|---------|
| P0 | Immediate | Immediate | If security | If UI | Immediate | Immediate |
| P1 | Immediate | Within 2h | If security | If UI | Same day | Same day |
| P2 | Same day | Next standup | No | If UI | No | No |
| P3 | Next sprint | No | No | If UI | No | No |

### Step 4: Investigation
1. **Reproduce**: Can we consistently trigger the bug?
2. **Scope**: How many users/features are affected?
3. **Root cause**: WHY did this happen? (not just WHAT is broken)
4. **Impact assessment**: What's the blast radius?
5. **Regression check**: Did a recent change cause this?

### Step 5: Fix
1. Identify the root cause (no band-aids for P0/P1)
2. Write the fix
3. Write a regression test that would have caught this
4. Self-review the fix for side effects
5. If P0: get second-eye review from another agent
6. Deploy the fix

### Step 6: Verification
1. Verify the fix resolves the original issue
2. Verify the regression test passes
3. Verify no new issues introduced
4. If P0: monitor for 1 hour after deploy
5. Update incident status to RESOLVED

### Step 7: Post-Mortem (P0 and P1 only)
Write post-mortem to `org/decisions/{date}-incident-{slug}.md`:

```markdown
# Incident Post-Mortem: {title}
Date: {YYYY-MM-DD}
Severity: P{0/1}
Duration: {time from detection to resolution}
Impact: {who was affected, how}

## Timeline
- {HH:MM} — Incident detected by {who/what}
- {HH:MM} — Severity classified as P{X}
- {HH:MM} — Investigation started
- {HH:MM} — Root cause identified: {description}
- {HH:MM} — Fix deployed
- {HH:MM} — Verified resolved

## Root Cause
{Detailed explanation of why this happened}

## Fix Applied
{What was changed and why}

## What Went Well
- {positive aspect of response}

## What Went Poorly
- {area for improvement}

## Action Items (prevent recurrence)
| Action | Owner | Deadline | Status |
|--------|-------|---------|--------|
| {action} | {dept} | {date} | Open |
| Add regression test | Quality | {date} | Open |

## Lessons Learned
{What we learned from this incident}
```

---

## Escalation Protocol

### When to Escalate
- P0 not resolved within 1 hour -> escalate to Founder
- P1 not resolved within 4 hours -> escalate to Operations
- Any incident affecting user data -> escalate to Security immediately
- Root cause unclear after 30 minutes -> bring in additional agents
- Fix requires architecture change -> escalate to Founder for approval

### Escalation Chain
1. Department Head (CTO for engineering issues)
2. Operations (COO for cross-department coordination)
3. Founder (for strategic decisions, architecture changes, user communication)

---

## Incident Tracking

All open incidents tracked in a running log:

```markdown
## Open Incidents
| ID | Severity | Description | Owner | Status | Opened |
|----|----------|------------|-------|--------|--------|
| {id} | P{X} | {desc} | {dept} | Investigating/Fixing/Verifying | {date} |

## Recently Resolved
| ID | Severity | Description | Resolution | Duration | Post-Mortem |
|----|----------|------------|-----------|----------|-------------|
| {id} | P{X} | {desc} | {how fixed} | {time} | {link or N/A} |
```

---

## Prevention

### Proactive Measures
1. **Quality department** runs regression tests on every change
2. **Design department** checks for visual regressions
3. **Security department** scans for vulnerabilities weekly
4. **Data department** monitors error rates and anomalies
5. **Engineering** maintains tech debt score above 7/10

### Incident Metrics
Track monthly:
- Total incidents by severity
- Mean time to detection (MTTD)
- Mean time to resolution (MTTR)
- Incidents caused by regressions (should be 0)
- Repeat incidents (same root cause — should be 0)
